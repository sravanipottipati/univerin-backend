import razorpay
import hmac
import hashlib
import os
from decimal import Decimal
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from orders.models import Order

def get_razorpay_client():
    key_id     = os.environ.get('RAZORPAY_KEY_ID', '')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    return razorpay.Client(auth=(key_id, key_secret))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_order(request):
    """Create Razorpay order for online payment"""
    try:
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({'error': 'order_id is required'}, status=400)

        # Get the order
        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        # Amount in paise (multiply by 100)
        amount_paise = int(float(order.total_amount) * 100)

        # Create Razorpay order
        client = get_razorpay_client()
        razorpay_order = client.order.create({
            'amount':   amount_paise,
            'currency': 'INR',
            'receipt':  str(order.order_number),
            'notes': {
                'order_id':   str(order.id),
                'buyer':      str(request.user.phone_number),
                'shop':       str(order.vendor.shop_name),
            }
        })

        return Response({
            'razorpay_order_id': razorpay_order['id'],
            'amount':            amount_paise,
            'currency':          'INR',
            'key_id':            os.environ.get('RAZORPAY_KEY_ID', ''),
            'order_number':      order.order_number,
            'shop_name':         order.vendor.shop_name,
        })

    except Exception as e:
        print(f'[Razorpay] Create order error: {e}')
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """Verify Razorpay payment signature and update order"""
    try:
        razorpay_order_id   = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature  = request.data.get('razorpay_signature')
        order_id            = request.data.get('order_id')

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, order_id]):
            return Response({'error': 'Missing payment details'}, status=400)

        # Verify signature
        key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        message    = f'{razorpay_order_id}|{razorpay_payment_id}'
        signature  = hmac.new(
            key_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if signature != razorpay_signature:
            return Response({'error': 'Invalid payment signature'}, status=400)

        # Update order payment status
        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
            order.payment_mode   = 'online'
            order.payment_status = 'paid'
            order.razorpay_order_id   = razorpay_order_id
            order.razorpay_payment_id = razorpay_payment_id
            order.save()
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        return Response({
            'success':            True,
            'message':            'Payment verified successfully',
            'razorpay_payment_id': razorpay_payment_id,
        })

    except Exception as e:
        print(f'[Razorpay] Verify payment error: {e}')
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def payment_failed(request):
    """Handle failed payment"""
    try:
        order_id = request.data.get('order_id')
        if order_id:
            try:
                order = Order.objects.get(id=order_id, buyer=request.user)
                order.payment_mode   = 'cod'  # fallback to COD
                order.save()
            except Order.DoesNotExist:
                pass
        return Response({'message': 'Payment failure recorded'})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_razorpay_only(request):
    """Create a Razorpay order using server-validated checkout pricing."""
    from vendors.models import Vendor
    from orders.models import RazorpayCheckout
    from orders.checkout_pricing import calculate_checkout_total
    from django.core.serializers.json import DjangoJSONEncoder
    import json

    data = request.data

    try:
        vendor = Vendor.objects.get(
            id=data.get('vendor_id'),
            status='approved',
        )
    except (Vendor.DoesNotExist, ValueError, TypeError):
        return Response(
            {'error': 'Shop not found or not approved'},
            status=404,
        )

    if not vendor.bank_account_number or not vendor.bank_ifsc_code:
        return Response(
            {'error': 'This shop is currently not accepting orders.'},
            status=400,
        )

    address = data.get('delivery_address')
    if not isinstance(address, str) or not address.strip():
        return Response(
            {'error': 'A delivery address is required.'},
            status=400,
        )

    latitude = data.get('delivery_latitude')
    longitude = data.get('delivery_longitude')

    try:
        checkout = calculate_checkout_total(
            vendor,
            data.get('items'),
            latitude,
            longitude,
        )
    except (ValueError, TypeError, OverflowError) as exc:
        return Response({'error': str(exc)}, status=400)

    snapshot = {
        'vendor_id': str(vendor.pk),
        'delivery_address': address.strip(),
        'delivery_latitude': float(latitude),
        'delivery_longitude': float(longitude),
        'notes': str(data.get('notes') or ''),
        'items': [
            {
                'product_id': str(item['product'].pk),
                'variant_id': (
                    str(item['variant'].pk)
                    if item['variant'] is not None else None
                ),
                'quantity': item['quantity'],
                'price': str(item['price']),
                'gst_rate': str(item['gst_rate']),
                'line_total': str(item['line_total']),
            }
            for item in checkout['items']
        ],
        'subtotal': str(checkout['subtotal']),
        'delivery_fee_incl_gst': str(checkout['delivery_fee_incl_gst']),
        'platform_fee': str(checkout['platform_fee']),
        'platform_fee_with_gst': str(checkout['platform_fee_with_gst']),
        'total': str(checkout['total']),
    }

    snapshot = json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))

    checkout_record = RazorpayCheckout.objects.create(
        buyer=request.user,
        vendor=vendor,
        amount_paise=checkout['amount_paise'],
        snapshot=snapshot,
    )

    try:
        client = get_razorpay_client()
        razorpay_order = client.order.create({
            'amount': checkout_record.amount_paise,
            'currency': 'INR',
            'receipt': str(checkout_record.id),
        })

        checkout_record.razorpay_order_id = razorpay_order['id']
        checkout_record.save(update_fields=['razorpay_order_id', 'updated_at'])

    except Exception:
        # Preserve the record for investigation/reconciliation.
        # Do not expose Razorpay credentials or internal errors to clients.
        return Response(
            {'error': 'Unable to create payment order. Please try again.'},
            status=503,
        )

    return Response({
        'razorpay_order_id': checkout_record.razorpay_order_id,
        'amount': checkout_record.amount_paise,
        'currency': 'INR',
        'key_id': os.environ.get('RAZORPAY_KEY_ID', ''),
        'shop_name': vendor.shop_name,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_order_after_payment(request):
    """Confirm a captured payment and create one order from its trusted snapshot."""
    import logging
    from django.db import transaction, IntegrityError
    from orders.models import (
        Order, OrderItem, RazorpayCheckout, generate_order_number,
    )
    from orders.serializers import OrderSerializer
    from orders.views import create_notification
    from vendors.models import Product, ProductVariant

    logger = logging.getLogger(__name__)

    if request.user.user_type != 'buyer':
        return Response({'error': 'Only buyers can place orders'}, status=403)

    razorpay_order_id = request.data.get('razorpay_order_id')
    razorpay_payment_id = request.data.get('razorpay_payment_id')
    razorpay_signature = request.data.get('razorpay_signature')

    if not all([
        isinstance(value, str) and value.strip()
        for value in (razorpay_order_id, razorpay_payment_id, razorpay_signature)
    ]):
        return Response({'error': 'Missing payment details'}, status=400)

    try:
        checkout = RazorpayCheckout.objects.select_related('order').get(
            razorpay_order_id=razorpay_order_id,
            buyer=request.user,
        )
    except RazorpayCheckout.DoesNotExist:
        return Response({'error': 'Checkout not found'}, status=404)

    secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    if not secret:
        return Response({'error': 'Payment verification unavailable'}, status=503)

    message = f'{razorpay_order_id}|{razorpay_payment_id}'
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, razorpay_signature):
        return Response({'error': 'Invalid payment signature'}, status=400)

    # A completed checkout may be retried safely.
    if checkout.order_id:
        existing = checkout.order
        if (
            existing.razorpay_payment_id != razorpay_payment_id
            or existing.razorpay_order_id != razorpay_order_id
        ):
            return Response({'error': 'Payment mismatch'}, status=409)
        return Response({'order': OrderSerializer(existing).data}, status=200)

    # Network calls happen before acquiring the database row lock.
    try:
        client = get_razorpay_client()
        payment = client.payment.fetch(razorpay_payment_id)
        payment_order = client.order.fetch(razorpay_order_id)
    except Exception:
        logger.exception('Unable to verify Razorpay payment')
        return Response(
            {'error': 'Payment verification temporarily unavailable. Retry confirmation.'},
            status=503,
        )

    try:
        paid_amount = int(payment.get('amount'))
        order_amount = int(payment_order.get('amount'))
    except (TypeError, ValueError, OverflowError):
        return Response({'error': 'Invalid payment amount'}, status=400)

    if (
        payment.get('order_id') != razorpay_order_id
        or payment.get('status') != 'captured'
        or payment.get('currency') != 'INR'
        or payment_order.get('id') != razorpay_order_id
        or payment_order.get('currency') != 'INR'
        or paid_amount != checkout.amount_paise
        or order_amount != checkout.amount_paise
    ):
        return Response({'error': 'Payment amount or status mismatch'}, status=400)


    return _create_order_from_verified_checkout(
        checkout, razorpay_order_id, razorpay_payment_id, request.user
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def razorpay_checkout_status(request):
    """Read-only recovery status for a buyer's Razorpay checkout."""
    import logging
    from orders.models import RazorpayCheckout
    from orders.serializers import OrderSerializer

    logger = logging.getLogger(__name__)

    if request.user.user_type != 'buyer':
        return Response({'error': 'Only buyers can check payments'}, status=403)

    razorpay_order_id = request.data.get('razorpay_order_id')

    if not isinstance(razorpay_order_id, str) or not razorpay_order_id.strip():
        return Response({'error': 'razorpay_order_id is required'}, status=400)

    try:
        checkout = RazorpayCheckout.objects.select_related('order').get(
            razorpay_order_id=razorpay_order_id,
            buyer=request.user,
        )
    except RazorpayCheckout.DoesNotExist:
        return Response({'error': 'Checkout not found'}, status=404)

    if checkout.order_id:
        return Response({
            'status': 'confirmed',
            'order': OrderSerializer(checkout.order).data,
        })

    try:
        client = get_razorpay_client()
        remote_order = client.order.fetch(razorpay_order_id)
        payments_result = client.order.payments(razorpay_order_id)
    except Exception:
        logger.exception('Unable to retrieve Razorpay checkout status')
        return Response({
            'status': 'verification_unavailable',
            'message': 'Payment status could not be verified. Do not pay again.',
        }, status=503)

    try:
        if (
            remote_order.get('id') != razorpay_order_id
            or remote_order.get('currency') != 'INR'
            or int(remote_order.get('amount')) != checkout.amount_paise
        ):
            return Response({
                'status': 'verification_unavailable',
                'message': 'Payment order details do not match. Contact support.',
            }, status=409)

        if not isinstance(payments_result, dict):
            raise ValueError('Invalid Razorpay payment response')

        payments = payments_result.get('items')
        if not isinstance(payments, list):
            raise ValueError('Missing Razorpay payment list')

        if (
            int(payments_result.get('count', -1)) != len(payments)
            or len(payments) >= 10
        ):
            return Response({
                'status': 'verification_unavailable',
                'message': 'Payment history requires further verification.',
            }, status=409)

        captured = []
        pending = []

        for payment in payments:
            if (
                payment.get('order_id') != razorpay_order_id
                or payment.get('currency') != 'INR'
                or int(payment.get('amount')) != checkout.amount_paise
            ):
                return Response({
                    'status': 'verification_unavailable',
                    'message': 'Payment details do not match. Contact support.',
                }, status=409)

            payment_status = payment.get('status')

            if payment_status == 'captured':
                captured.append(payment)
            elif payment_status in ('authorized', 'created', 'pending'):
                pending.append(payment)
            elif payment_status != 'failed':
                pending.append(payment)

        if len(captured) > 1:
            return Response({
                'status': 'verification_unavailable',
                'message': 'Multiple captured payments require reconciliation. Do not pay again.',
            }, status=409)

        if captured:
            return Response({
                'status': 'captured_unconfirmed',
                'message': 'Payment was captured. Order recovery is required. Do not pay again.',
            })

        if pending:
            return Response({
                'status': 'pending',
                'message': 'Payment may still be processing. Do not pay again.',
            })

        return Response({
            'status': 'unpaid',
            'message': 'No captured payment was found at this time. Do not retry payment until checkout recovery is completed.',
        })

    except (TypeError, ValueError, OverflowError, AttributeError):
        logger.exception('Invalid Razorpay checkout status response')
        return Response({
            'status': 'verification_unavailable',
            'message': 'Payment status could not be verified. Do not pay again.',
        }, status=503)



def _create_order_from_verified_checkout(
    checkout, razorpay_order_id, razorpay_payment_id, buyer
):
    """Create or return an order after trusted payment verification."""
    import logging
    from django.db import transaction, IntegrityError
    from orders.models import (
        Order, OrderItem, RazorpayCheckout, generate_order_number,
    )
    from orders.serializers import OrderSerializer
    from orders.views import create_notification
    from vendors.models import Product, ProductVariant

    logger = logging.getLogger(__name__)
    try:
        with transaction.atomic():
            locked = (
                RazorpayCheckout.objects
                .select_for_update(of=('self',))
                .select_related('vendor', 'order')
                .get(pk=checkout.pk)
            )

            if locked.order_id:
                existing = Order.objects.get(pk=locked.order_id)
                if (
                    existing.razorpay_payment_id != razorpay_payment_id
                    or existing.razorpay_order_id != razorpay_order_id
                ):
                    return Response({'error': 'Payment mismatch'}, status=409)
                return Response({'order': OrderSerializer(existing).data}, status=200)

            if Order.objects.filter(razorpay_payment_id=razorpay_payment_id).exists():
                return Response(
                    {'error': 'Payment already associated with another order'},
                    status=409,
                )

            snapshot = locked.snapshot
            vendor = locked.vendor

            if not isinstance(snapshot, dict) or not snapshot.get('items'):
                return Response({'error': 'Invalid saved checkout'}, status=409)

            if snapshot.get('vendor_id') != str(vendor.pk):
                return Response({'error': 'Checkout vendor mismatch'}, status=409)

            subtotal = Decimal(snapshot['subtotal'])
            platform_fee = Decimal(snapshot['platform_fee'])
            delivery_fee_incl_gst = Decimal(snapshot['delivery_fee_incl_gst'])
            grand_total = Decimal(snapshot['total'])

            if int(grand_total * 100) != locked.amount_paise:
                return Response({'error': 'Checkout amount mismatch'}, status=409)

            order_items = []
            for item in snapshot['items']:
                product = Product.objects.get(
                    pk=item['product_id'],
                    vendor=vendor,
                )
                variant = None
                if item.get('variant_id'):
                    variant = ProductVariant.objects.get(
                        pk=item['variant_id'],
                        product=product,
                    )

                order_items.append({
                    'product': product,
                    'variant': variant,
                    'quantity': int(item['quantity']),
                    'price': Decimal(item['price']),
                    'gst_rate': Decimal(item['gst_rate']),
                })

            delivery_fee = (
                delivery_fee_incl_gst / Decimal('1.18')
            ).quantize(Decimal('0.01'))
            gst_on_delivery = delivery_fee_incl_gst - delivery_fee

            category = (vendor.category or '').lower()
            if category in ('vegetables', 'fruits'):
                commission_rate = Decimal('3.0')
            elif category in (
                'restaurant', 'bakery', 'fast_food', 'chinese', 'ice_cream'
            ):
                commission_rate = Decimal('20.0')
            else:
                commission_rate = Decimal('6.0')

            commission_amount = (
                subtotal * commission_rate / Decimal('100')
            ).quantize(Decimal('0.01'))
            gst_on_platform = (
                (platform_fee + delivery_fee) * Decimal('0.18')
            ).quantize(Decimal('0.01'))
            tcs_amount = (
                subtotal * Decimal('0.01')
            ).quantize(Decimal('0.01'))

            order = Order.objects.create(
                order_number=generate_order_number(vendor=vendor),
                buyer=buyer,
                vendor=vendor,
                subtotal=subtotal,
                platform_fee=platform_fee,
                delivery_fee=delivery_fee,
                gst_on_delivery=gst_on_delivery,
                commission_rate=commission_rate,
                commission_amount=commission_amount,
                gst_on_platform=gst_on_platform,
                tcs_amount=tcs_amount,
                total_amount=grand_total,
                delivery_address=snapshot['delivery_address'],
                delivery_latitude=snapshot['delivery_latitude'],
                delivery_longitude=snapshot['delivery_longitude'],
                instructions=snapshot.get('notes', ''),
                payment_mode='online',
                payment_status='paid',
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                status='placed',
            )

            for item in order_items:
                OrderItem.objects.create(
                    order=order,
                    product=item['product'],
                    variant=item['variant'],
                    quantity=item['quantity'],
                    price=item['price'],
                    gst_rate_at_purchase=item['gst_rate'],
                    gst_pricing_mode_at_purchase=getattr(
                        item['product'], 'gst_pricing_mode', 'exclusive'
                    ),
                )

            locked.order = order
            locked.status = 'confirmed'
            locked.save(update_fields=['order', 'status', 'updated_at'])

            def notify_after_commit():
                create_notification(
                    user=vendor.user,
                    notif_type='new_order',
                    title='New Order Received',
                    message=(
                        f'Order #{str(order.id)[:8].upper()} '
                        f'received for ₹{order.subtotal}'
                    ),
                    order=order,
                )
                create_notification(
                    user=buyer,
                    notif_type='order_placed',
                    title='Order Placed Successfully',
                    message=f'Your order from {vendor.shop_name} has been placed!',
                    order=order,
                )

            transaction.on_commit(notify_after_commit)

        return Response({'order': OrderSerializer(order).data}, status=201)

    except IntegrityError:
        logger.exception('Payment confirmation database conflict')
        return Response(
            {'error': 'Payment confirmation conflict. Please retry.'},
            status=409,
        )
    except Exception:
        logger.exception('Payment confirmation failed')
        return Response(
            {'error': 'Unable to confirm payment. Please retry confirmation.'},
            status=503,
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recover_razorpay_checkout(request):
    """Recover an interrupted checkout using server-verified Razorpay data."""
    import logging
    from orders.models import RazorpayCheckout
    from orders.serializers import OrderSerializer

    logger = logging.getLogger(__name__)

    if request.user.user_type != 'buyer':
        return Response({'error': 'Only buyers can recover payments'}, status=403)

    razorpay_order_id = request.data.get('razorpay_order_id')
    if not isinstance(razorpay_order_id, str) or not razorpay_order_id.strip():
        return Response({'error': 'razorpay_order_id is required'}, status=400)

    try:
        checkout = RazorpayCheckout.objects.select_related('order').get(
            razorpay_order_id=razorpay_order_id,
            buyer=request.user,
        )
    except RazorpayCheckout.DoesNotExist:
        return Response({'error': 'Checkout not found'}, status=404)

    if checkout.order_id:
        return Response({'order': OrderSerializer(checkout.order).data}, status=200)

    try:
        client = get_razorpay_client()
        remote_order = client.order.fetch(razorpay_order_id)
        result = client.order.payments(razorpay_order_id)

        if (
            remote_order.get('id') != razorpay_order_id
            or remote_order.get('currency') != 'INR'
            or int(remote_order.get('amount')) != checkout.amount_paise
        ):
            return Response({'error': 'Payment order mismatch'}, status=409)

        if not isinstance(result, dict) or not isinstance(result.get('items'), list):
            return Response({'error': 'Payment verification incomplete'}, status=409)

        payments = result['items']

        if (
            int(result.get('count', -1)) != len(payments)
            or len(payments) >= 10
        ):
            return Response({'error': 'Payment history requires reconciliation'}, status=409)

        captured = []
        pending = []

        for payment in payments:
            if (
                not isinstance(payment, dict)
                or payment.get('order_id') != razorpay_order_id
                or payment.get('currency') != 'INR'
                or int(payment.get('amount')) != checkout.amount_paise
            ):
                return Response({'error': 'Payment details mismatch'}, status=409)

            payment_status = payment.get('status')

            if payment_status == 'captured':
                captured.append(payment)
            elif payment_status != 'failed':
                pending.append(payment)

        if len(captured) > 1:
            return Response({'error': 'Multiple captured payments require reconciliation'}, status=409)

        if not captured:
            if pending:
                return Response({
                    'status': 'pending',
                    'message': 'Payment is still processing. Do not pay again.',
                }, status=409)

            return Response({
                'status': 'unpaid',
                'message': 'No captured payment verified. Do not pay again until resolved.',
            }, status=409)

        payment_id = captured[0].get('id')
        if not isinstance(payment_id, str) or not payment_id.strip():
            return Response({'error': 'Invalid captured payment ID'}, status=409)

        verified_payment = client.payment.fetch(payment_id)

        if (
            verified_payment.get('id') != payment_id
            or verified_payment.get('order_id') != razorpay_order_id
            or verified_payment.get('status') != 'captured'
            or verified_payment.get('currency') != 'INR'
            or int(verified_payment.get('amount')) != checkout.amount_paise
        ):
            return Response({'error': 'Captured payment verification failed'}, status=409)

    except (TypeError, ValueError, OverflowError, AttributeError):
        logger.exception('Invalid Razorpay recovery response')
        return Response({'error': 'Payment verification unavailable. Do not pay again.'}, status=503)
    except Exception:
        logger.exception('Razorpay recovery service failure')
        return Response({'error': 'Payment verification unavailable. Do not pay again.'}, status=503)

    return _create_order_from_verified_checkout(
        checkout, razorpay_order_id, payment_id, request.user
    )
