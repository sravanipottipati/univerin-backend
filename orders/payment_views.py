import razorpay
import hmac
import hashlib
import os
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
