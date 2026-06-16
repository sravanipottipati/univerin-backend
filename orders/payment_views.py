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
    """Create Razorpay order WITHOUT placing Univerin order first"""
    try:
        amount = request.data.get('amount')
        shop_name = request.data.get('shop_name', 'Shop')
        if not amount:
            return Response({'error': 'amount is required'}, status=400)
        amount_paise = int(float(amount) * 100)
        client = get_razorpay_client()
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f'temp_{request.user.phone_number}',
        })
        return Response({
            'razorpay_order_id': razorpay_order['id'],
            'amount': amount_paise,
            'currency': 'INR',
            'key_id': os.environ.get('RAZORPAY_KEY_ID', ''),
            'shop_name': shop_name,
        })
    except Exception as e:
        print(f'[Razorpay] Create order error: {e}')
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_order_after_payment(request):
    """Place order only after Razorpay payment is verified"""
    try:
        razorpay_order_id   = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature  = request.data.get('razorpay_signature')
        order_data          = request.data.get('order_data')

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, order_data]):
            return Response({'error': 'Missing payment or order details'}, status=400)

        # Verify Razorpay signature first
        key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        message    = f'{razorpay_order_id}|{razorpay_payment_id}'
        signature  = hmac.new(
            key_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if signature != razorpay_signature:
            return Response({'error': 'Invalid payment signature'}, status=400)

        # Payment verified! Now create the order using PlaceOrderView logic
        from vendors.models import Vendor, Product
        from orders.models import Order, OrderItem, generate_order_number, Notification
        from decimal import Decimal

        try:
            vendor = Vendor.objects.get(id=order_data['vendor_id'], status='approved')
        except Vendor.DoesNotExist:
            return Response({'error': 'Shop not found or not approved'}, status=404)

        # Block order if vendor has no bank details
        if not vendor.bank_account_number or not vendor.bank_ifsc_code:
            return Response({'error': 'This shop is currently not accepting orders.'}, status=400)

        # Build order items
        order_items = []
        total_amount = Decimal('0')
        for item in order_data.get('items', []):
            try:
                product  = Product.objects.get(id=item['product_id'], vendor=vendor, is_available=True)
                quantity = int(item['quantity'])
                price    = Decimal(str(item['price']))
                total_amount += price * quantity

                variant = None
                if item.get('variant_id'):
                    try:
                        from vendors.models import ProductVariant
                        variant = ProductVariant.objects.get(id=item['variant_id'])
                    except Exception:
                        pass
                order_items.append({'product': product, 'quantity': quantity, 'price': price, 'variant': variant})
            except Product.DoesNotExist:
                return Response({'error': f"Product {item['product_id']} not found"}, status=404)

        # Fee structure
        platform_fee = Decimal('10')
        delivery_fee_incl_gst = Decimal(str(order_data.get('delivery_fee', 0)))
        delivery_fee     = round(delivery_fee_incl_gst / Decimal('1.18'), 2)
        gst_on_delivery  = round(delivery_fee_incl_gst - delivery_fee, 2)

        category = vendor.category.lower() if vendor.category else ''
        if category in ['vegetables', 'fruits']:
            commission_rate = Decimal('3.0')
        elif category in ['restaurant', 'bakery', 'fast_food', 'chinese', 'ice_cream']:
            commission_rate = Decimal('20.0')
        else:
            commission_rate = Decimal('6.0')

        subtotal          = total_amount
        commission_amount = round(subtotal * commission_rate / 100, 2)
        gst_on_platform   = round((platform_fee + delivery_fee) * Decimal('0.18'), 2)
        tcs_amount        = round(subtotal * Decimal('0.01'), 2)
        platform_fee_gst  = round(platform_fee * Decimal('1.18'), 0)
        grand_total       = Decimal(str(order_data.get('total', 0)))
        if grand_total <= 0:
            grand_total = subtotal + platform_fee_gst + delivery_fee

        order_num = generate_order_number(vendor=vendor)

        order = Order.objects.create(
            order_number=order_num,
            buyer=request.user,
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
            delivery_address=order_data['delivery_address'],
            instructions=order_data.get('notes', ''),
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
                variant=item.get('variant'),
                quantity=item['quantity'],
                price=item['price'],
            )

        # Notify vendor
        Notification.objects.create(
            user=vendor.user,
            type='new_order',
            title='New Order Received',
            message=f'Order #{str(order.id)[:8].upper()} received for ₹{order.total_amount}',
            order=order,
        )
        # Notify buyer
        Notification.objects.create(
            user=request.user,
            type='order_placed',
            title='Order Placed Successfully',
            message=f'Your order from {vendor.shop_name} has been placed!',
            order=order,
        )

        from orders.serializers import OrderSerializer
        return Response({'order': OrderSerializer(order).data}, status=201)

    except Exception as e:
        import traceback
        print(f'[PlaceAfterPay] Error: {e}')
        print(traceback.format_exc())
        return Response({'error': str(e)}, status=500)