import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status
from django.utils import timezone

from .models import Order
from django.db.models import Sum


def _is_dp(request):
    return request.user.user_type == 'delivery_partner'


class DPAvailableOrdersView(APIView):
    """
    GET /dp/orders/available/
    Lists orders ready for pickup that no delivery partner has taken yet.
    Basic version: any order with status='preparing' or 'dispatched' and dp_status='unassigned'.
    No geo-matching yet — shows all such orders to any online, approved DP.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        orders = Order.objects.filter(
            status__in=['preparing', 'dispatched'],
            dp_status='unassigned',
        ).order_by('created_at')

        data = [{
            'id': str(o.id),
            'order_number': o.order_number,
            'shop_name': o.vendor.shop_name,
            'shop_address': o.vendor.address,
            'delivery_address': o.delivery_address,
            'total_amount': str(o.total_amount),
            'delivery_fee': str(o.delivery_fee),
            'payment_mode': o.payment_mode,
            'created_at': o.created_at.isoformat(),
        } for o in orders]

        return Response(data, status=http_status.HTTP_200_OK)


class DPOrderAcceptView(APIView):
    """
    POST /dp/orders/<order_id>/accept/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=http_status.HTTP_404_NOT_FOUND)

        if order.dp_status != 'unassigned':
            return Response({'error': 'This order has already been taken by another delivery partner'}, status=http_status.HTTP_409_CONFLICT)

        order.delivery_partner = request.user
        order.dp_status = 'accepted'
        order.save(update_fields=['delivery_partner', 'dp_status', 'updated_at'])

        return Response({'message': 'Order accepted', 'order_id': str(order.id)}, status=http_status.HTTP_200_OK)


class DPOrderRejectView(APIView):
    """
    POST /dp/orders/<order_id>/reject/
    A no-op on the order itself for the basic version — just confirms the DP
    declined, so the frontend can remove it from that DP's local offer list.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)
        return Response({'message': 'Order declined'}, status=http_status.HTTP_200_OK)


class DPOrderStatusUpdateView(APIView):
    """
    POST /dp/orders/<order_id>/status/
    body: { "dp_status": "arrived_at_shop" }  (or picked_up, arrived_at_buyer)
    Generates a delivery OTP automatically when moving to picked_up.
    """
    permission_classes = [IsAuthenticated]

    VALID_TRANSITIONS = {
        'accepted':         'arrived_at_shop',
        'arrived_at_shop':  'picked_up',
        'picked_up':        'arrived_at_buyer',
    }

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        try:
            order = Order.objects.get(id=order_id, delivery_partner=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found or not assigned to you'}, status=http_status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('dp_status')
        expected_next = self.VALID_TRANSITIONS.get(order.dp_status)

        if new_status != expected_next:
            return Response(
                {'error': f'Invalid status transition from {order.dp_status} to {new_status}'},
                status=http_status.HTTP_400_BAD_REQUEST
            )

        order.dp_status = new_status

        # Generate delivery OTP the moment the order is picked up
        if new_status == 'picked_up':
            order.delivery_otp = str(random.randint(100000, 999999))
            order.status = 'dispatched'

        order.save()

        return Response({
            'message': 'Status updated',
            'dp_status': order.dp_status,
        }, status=http_status.HTTP_200_OK)


class DPVerifyDeliveryOTPView(APIView):
    """
    POST /dp/orders/<order_id>/verify-delivery-otp/
    body: { "otp": "123456" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        try:
            order = Order.objects.get(id=order_id, delivery_partner=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found or not assigned to you'}, status=http_status.HTTP_404_NOT_FOUND)

        if order.dp_status != 'arrived_at_buyer':
            return Response({'error': 'Order is not ready for delivery confirmation'}, status=http_status.HTTP_400_BAD_REQUEST)

        entered_otp = request.data.get('otp', '').strip()
        if entered_otp != order.delivery_otp:
            return Response({'error': 'Incorrect OTP. Please check with the customer.'}, status=http_status.HTTP_400_BAD_REQUEST)

        order.dp_status = 'delivered'
        order.status = 'delivered'
        order.save()

        return Response({'message': 'Delivery confirmed successfully'}, status=http_status.HTTP_200_OK)


class DPMyActiveOrderView(APIView):
    """
    GET /dp/orders/active/
    Returns the DP's current in-progress order, if any — used so the app can
    resume the active-order screen if reopened mid-delivery.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_dp(request):
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        order = Order.objects.filter(
            delivery_partner=request.user,
        ).exclude(dp_status__in=['delivered', 'unassigned']).first()

        if not order:
            return Response(None, status=http_status.HTTP_200_OK)

        return Response({
            'id': str(order.id),
            'order_number': order.order_number,
            'shop_name': order.vendor.shop_name,
            'shop_address': order.vendor.address,
            'delivery_address': order.delivery_address,
            'dp_status': order.dp_status,
            'total_amount': str(order.total_amount),
            'delivery_fee': str(order.delivery_fee),
            'payment_mode': order.payment_mode,
        }, status=http_status.HTTP_200_OK)
class DPEarningsView(APIView):
    """
    GET /dp/earnings/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'delivery_partner':
            return Response({'error': 'Not a delivery partner account'}, status=http_status.HTTP_403_FORBIDDEN)

        delivered_orders = Order.objects.filter(
            delivery_partner=request.user,
            dp_status='delivered',
        )

        today = timezone.now().date()
        today_orders = delivered_orders.filter(updated_at__date=today)

        today_total = today_orders.aggregate(total=Sum('delivery_fee'))['total'] or 0
        all_time_total = delivered_orders.aggregate(total=Sum('delivery_fee'))['total'] or 0

        return Response({
            'today_earnings': str(today_total),
            'today_deliveries': today_orders.count(),
            'all_time_earnings': str(all_time_total),
            'all_time_deliveries': delivered_orders.count(),
        }, status=http_status.HTTP_200_OK)