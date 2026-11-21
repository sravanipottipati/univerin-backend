"""
Razorpay refund workflow.

Refunds are disabled by default. Reserving a refund never
contacts Razorpay or transfers money.
"""

from decimal import Decimal

from django.db import transaction

from orders.models import Order, Refund


class RefundError(Exception):
    pass


@transaction.atomic
def reserve_order_refund(order_id, *, reason):
    """
    Reserve one full refund per eligible prepaid order.

    Existing reservations are returned without creating duplicates.
    No external payment calls occur here.
    """
    order = (
        Order.objects
        .select_for_update()
        .select_related("buyer")
        .get(pk=order_id)
    )

    if order.payment_mode != "online":
        raise RefundError("COD orders do not require online refunds.")

    if order.payment_status != "paid":
        raise RefundError("Order payment is not confirmed.")

    if not order.razorpay_payment_id or not order.razorpay_order_id:
        raise RefundError("Razorpay payment references are missing.")

    amount_paise = int(
        (Decimal(order.total_amount) * 100)
        .to_integral_value()
    )

    if amount_paise <= 0:
        raise RefundError("Invalid refund amount.")

    from orders.models import RazorpayCheckout

    checkout = RazorpayCheckout.objects.filter(
        order=order,
        status="confirmed",
    ).first()

    if checkout:
        if (
            checkout.razorpay_order_id != order.razorpay_order_id
            or checkout.amount_paise != amount_paise
        ):
            raise RefundError(
                "Order amount does not match original Razorpay checkout."
            )

    existing = Refund.objects.filter(order=order).first()

    if existing:
        if existing.processing_state == "not_started":
            raise RefundError(
                "An existing refund request requires review."
            )
        return existing, False

    refund = Refund.objects.create(
        order=order,
        requested_by=order.buyer,
        reason=reason,
        status="requested",
        processing_state="reserved",
        razorpay_payment_id=order.razorpay_payment_id,
        amount_paise=amount_paise,
    )

    return refund, True


def process_reserved_refund(refund_id):
    """
    Initiate an eligible reserved refund at most once.

    External refund execution is disabled by default.
    Ambiguous provider outcomes require reconciliation, never blind retry.
    """
    from django.conf import settings
    from django.utils import timezone

    if not getattr(settings, "RAZORPAY_AUTO_REFUNDS_ENABLED", False):
        raise RefundError("Automatic Razorpay refunds are disabled.")

    with transaction.atomic():
        refund = (
            Refund.objects.select_for_update()
            .select_related("order")
            .get(pk=refund_id)
        )

        if refund.processing_state != "reserved":
            raise RefundError("Refund is not available for initiation.")

        if refund.order.status not in ("rejected", "cancelled"):
            raise RefundError("Order has not been rejected or cancelled.")

        # Claim before any external API call. A crash or timeout must not
        # cause a later worker to issue a second refund automatically.
        refund.processing_state = "initiated"
        refund.initiated_at = timezone.now()
        refund.save(update_fields=["processing_state", "initiated_at", "updated_at"])

        payment_id = refund.razorpay_payment_id
        razorpay_order_id = refund.order.razorpay_order_id
        amount = refund.amount_paise
        order_id = str(refund.order_id)

    try:
        from orders.payment_views import get_razorpay_client

        client = get_razorpay_client()
        payment = client.payment.fetch(payment_id)

        if (
            payment.get("id") != payment_id
            or payment.get("order_id") != razorpay_order_id
            or payment.get("currency") != "INR"
            or payment.get("status") != "captured"
            or payment.get("captured") is not True
            or payment.get("amount") != amount
            or payment.get("amount_refunded", 0) != 0
        ):
            raise RefundError("Razorpay payment verification failed.")

        result = client.payment.refund(
            payment_id,
            {
                "amount": amount,
                "speed": "normal",
                "receipt": f"univerin-{order_id[:24]}",
                "notes": {"order_id": order_id},
            },
        )

        if (
            not result.get("id")
            or result.get("payment_id") != payment_id
            or result.get("amount") != amount
            or result.get("currency") != "INR"
        ):
            raise RefundError("Unexpected Razorpay refund response.")

    except Exception as exc:
        Refund.objects.filter(
            pk=refund_id,
            processing_state="initiated",
            razorpay_refund_id__isnull=True,
        ).update(
            processing_state="requires_review",
            failure_reason=str(exc)[:2000],
        )
        raise RefundError(
            "Refund outcome requires reconciliation before any retry."
        ) from exc

    provider_status = result.get("status")

    if provider_status == "processed":
        next_state = "completed"
    elif provider_status in ("pending", "created", "processing"):
        next_state = "initiated"
    else:
        next_state = "requires_review"

    completed = next_state == "completed"

    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)

        if refund.processing_state != "initiated":
            raise RefundError("Refund state changed during processing.")

        refund.razorpay_refund_id = result["id"]
        refund.processing_state = next_state
        refund.status = "processed" if completed else refund.status
        refund.completed_at = timezone.now() if completed else None
        refund.failure_reason = (
            f"Razorpay returned status: {provider_status!r}; review required."
            if next_state == "requires_review" else ""
        )
        refund.save(update_fields=[
            "razorpay_refund_id",
            "processing_state",
            "status",
            "completed_at",
            "failure_reason",
            "updated_at",
        ])

    return refund


@transaction.atomic
def transition_order_with_refund(order_id, *, target_status):
    """
    Atomically cancel/reject a placed order and reserve its refund.
    Does not call Razorpay.
    """
    if target_status not in ("rejected", "cancelled"):
        raise RefundError("Unsupported refund transition.")

    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != "placed":
        raise RefundError(
            "Only placed orders can be rejected or cancelled."
        )

    order.status = target_status
    order.save(update_fields=["status"])

    if order.payment_mode == "online":
        reserve_order_refund(
            order.pk,
            reason=(
                "Seller rejected order"
                if target_status == "rejected"
                else "Buyer cancelled order"
            ),
        )

    return order


def reconcile_order_refund(refund_id):
    """
    Refresh a known Razorpay refund's status.
    Read-only against Razorpay: never creates another refund.
    """
    from django.utils import timezone
    from orders.payment_views import get_razorpay_client

    refund = Refund.objects.get(pk=refund_id)

    if not refund.razorpay_refund_id:
        raise RefundError(
            "Refund ID is missing; manual reconciliation is required."
        )

    if refund.processing_state == "completed":
        return refund

    try:
        result = get_razorpay_client().refund.fetch(
            refund.razorpay_refund_id
        )
    except Exception as exc:
        raise RefundError(
            "Unable to fetch Razorpay refund status."
        ) from exc

    if (
        result.get("id") != refund.razorpay_refund_id
        or result.get("payment_id") != refund.razorpay_payment_id
        or result.get("amount") != refund.amount_paise
        or result.get("currency") != "INR"
    ):
        raise RefundError("Razorpay refund details do not match.")

    provider_status = result.get("status")

    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund_id)

        if refund.processing_state == "completed":
            return refund

        if provider_status == "processed":
            refund.processing_state = "completed"
            refund.status = "processed"
            refund.completed_at = timezone.now()
            refund.failure_reason = ""
        elif provider_status == "failed":
            refund.processing_state = "requires_review"
            refund.failure_reason = (
                "Razorpay reports refund failed; manual review required."
            )
        elif provider_status in ("created", "pending", "processing"):
            refund.processing_state = "initiated"
            refund.failure_reason = ""
        else:
            raise RefundError(
                "Unknown Razorpay refund status; manual review required."
            )

        refund.save(update_fields=[
            "processing_state",
            "status",
            "completed_at",
            "failure_reason",
            "updated_at",
        ])

    return refund
