from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from delivery_partner.matching import find_nearby_delivery_partners
from orders.models import Order, DeliveryOffer


def create_next_delivery_offer(order_id):
    """
    Create a 30-second offer for the nearest eligible DP.

    Returns the new DeliveryOffer, or None when dispatch
    cannot proceed.
    """
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .select_related("vendor")
            .get(pk=order_id)
        )

        # Dispatch only for active, Seller-accepted orders.
        if order.status not in ["accepted", "preparing"]:
            return None

        # Do not offer an order already assigned to a DP.
        if order.delivery_partner_id is not None:
            return None

        if order.dp_status not in ["unassigned", "offered"]:
            return None

        # Never create two simultaneous pending offers.
        if DeliveryOffer.objects.filter(
            order=order,
            status="pending",
        ).exists():
            return None

        candidates = find_nearby_delivery_partners(order.vendor)

        # Prefer partners who have never received this order.
        # Never retry a rejected or accepted offer.
        blocked_ids = set(
            DeliveryOffer.objects.filter(
                order=order,
                status__in=["rejected", "accepted", "pending"],
            ).values_list("delivery_partner_id", flat=True)
        )
        previously_offered_ids = set(
            DeliveryOffer.objects.filter(order=order)
            .values_list("delivery_partner_id", flat=True)
        )

        new_candidates = [
            (dp, distance_km)
            for dp, distance_km in candidates
            if dp.user_id not in previously_offered_ids
        ]
        expired_candidates = [
            (dp, distance_km)
            for dp, distance_km in candidates
            if dp.user_id in previously_offered_ids
            and dp.user_id not in blocked_ids
        ]

        for dp, distance_km in new_candidates + expired_candidates:
            offer = DeliveryOffer.objects.create(
                order=order,
                delivery_partner=dp.user,
                status="pending",
                expires_at=timezone.now() + timedelta(seconds=30),
            )

            order.dp_status = "offered"
            order.save(update_fields=["dp_status", "updated_at"])

            return offer

        return None


def expire_delivery_offer(offer_id):
    """
    Expire a pending offer whose deadline has passed, then
    attempt to offer the order to the next eligible partner.

    Returns True if an offer was expired; otherwise False.
    """
    with transaction.atomic():
        # Read the order ID without acquiring a row lock.
        try:
            offer_order_id = DeliveryOffer.objects.values_list(
                "order_id", flat=True
            ).get(pk=offer_id)
        except DeliveryOffer.DoesNotExist:
            return False

        # Consistent lock order: Order first, then DeliveryOffer.
        order = Order.objects.select_for_update().get(pk=offer_order_id)

        try:
            offer = DeliveryOffer.objects.select_for_update().get(
                pk=offer_id,
                order_id=order.id,
            )
        except DeliveryOffer.DoesNotExist:
            return False

        now = timezone.now()

        # Recheck after acquiring both locks.
        if offer.status != "pending" or offer.expires_at > now:
            return False

        offer.status = "expired"
        offer.responded_at = now
        offer.save(update_fields=["status", "responded_at"])

        # Do not retry for orders that are no longer dispatchable.
        if (
            order.delivery_partner_id is not None
            or order.status not in ["accepted", "preparing"]
            or order.dp_status not in ["unassigned", "offered"]
        ):
            return True

        order.dp_status = "unassigned"
        order.save(update_fields=["dp_status", "updated_at"])

    # Start the next offer outside the expiration transaction.
    create_next_delivery_offer(order.id)
    return True


def expire_due_delivery_offers():
    """
    Expire all offers that have reached their deadline.
    Returns the number successfully expired.
    """
    due_offer_ids = list(
        DeliveryOffer.objects.filter(
            status="pending",
            expires_at__lte=timezone.now(),
        ).values_list("id", flat=True)
    )

    expired_count = 0

    for offer_id in due_offer_ids:
        if expire_delivery_offer(offer_id):
            expired_count += 1

    return expired_count


def retry_recent_unassigned_orders(max_age_minutes=30):
    """
    Retry dispatch for recently created, unassigned orders.

    Existing dispatch safeguards prevent duplicate pending offers
    and repeated offers to the same delivery partner.
    """
    cutoff = timezone.now() - timedelta(minutes=max_age_minutes)

    order_ids = list(
        Order.objects.filter(
            status__in=["accepted", "preparing"],
            dp_status="unassigned",
            delivery_partner__isnull=True,
            created_at__gte=cutoff,
        )
        .order_by("created_at")
        .values_list("id", flat=True)
    )

    created_count = 0

    for order_id in order_ids:
        offer = create_next_delivery_offer(order_id)
        if offer is not None:
            created_count += 1

    return created_count
