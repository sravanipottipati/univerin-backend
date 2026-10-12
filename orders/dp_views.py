import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status as http_status
from django.utils import timezone
from django.db import transaction

from .models import Order, DeliveryOffer
from delivery_partner.models import DeliveryPartner
from django.db.models import Sum


def _is_dp(request):
    return request.user.user_type == 'delivery_partner'


class DPAvailableOrdersView(APIView):
    """
    GET /dp/orders/available/
    Show only active delivery offers addressed to the current DP.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_dp(request):
            return Response(
                {'error': 'Not a delivery partner account'},
                status=http_status.HTTP_403_FORBIDDEN
            )

        from orders.models import DeliveryOffer

        dp = DeliveryPartner.objects.filter(
            user_id=request.user.id,
            status='approved',
            is_online=True,
        ).first()

        if dp is None:
            return Response([], status=http_status.HTTP_200_OK)

        offers = (
            DeliveryOffer.objects.filter(
                delivery_partner=request.user,
                status='pending',
                expires_at__gt=timezone.now(),
                order__status__in=['accepted', 'preparing'],
                order__dp_status='offered',
                order__delivery_partner__isnull=True,
            )
            .select_related('order', 'order__vendor')
            .order_by('offered_at')
        )

        data = [{
            'id': str(offer.order.id),
            'order_number': offer.order.order_number,
            'shop_name': offer.order.vendor.shop_name,
            'shop_address': offer.order.vendor.address,
            'delivery_address': offer.order.delivery_address,
            'total_amount': str(offer.order.total_amount),
            'delivery_fee': str(offer.order.delivery_fee),
            'payment_mode': offer.order.payment_mode,
            'created_at': offer.order.created_at.isoformat(),
        } for offer in offers]

        return Response(data, status=http_status.HTTP_200_OK)


class DPOrderAcceptView(APIView):
    """
    POST /dp/orders/<order_id>/accept/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response(
                {'error': 'Not a delivery partner account'},
                status=http_status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            dp = DeliveryPartner.objects.select_for_update().filter(
                user_id=request.user.id
            ).first()

            if dp is None:
                return Response(
                    {'error': 'Complete onboarding first'},
                    status=http_status.HTTP_400_BAD_REQUEST
                )

            if dp.status != 'approved':
                return Response(
                    {'error': 'Your account is not yet approved'},
                    status=http_status.HTTP_403_FORBIDDEN
                )

            if not dp.is_online:
                return Response(
                    {'error': 'Go online before accepting orders'},
                    status=http_status.HTTP_403_FORBIDDEN
                )

            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                return Response(
                    {'error': 'Order not found'},
                    status=http_status.HTTP_404_NOT_FOUND
                )

            now = timezone.now()

            # Require an active, unexpired offer addressed to this DP.
            offer = (
                DeliveryOffer.objects.select_for_update()
                .filter(
                    order=order,
                    delivery_partner=request.user,
                    status='pending',
                )
                .first()
            )

            if offer is None:
                return Response(
                    {'error': 'No pending offer exists for this order'},
                    status=http_status.HTTP_409_CONFLICT
                )

            if offer.expires_at <= now:
                offer.status = 'expired'
                offer.responded_at = now
                offer.save(update_fields=['status', 'responded_at'])

                if order.delivery_partner_id is None and order.dp_status == 'offered':
                    order.dp_status = 'unassigned'
                    order.save(update_fields=['dp_status', 'updated_at'])

                from orders.dispatch_service import create_next_delivery_offer

                transaction.on_commit(
                    lambda order_id=order.id: create_next_delivery_offer(order_id)
                )

                return Response(
                    {'error': 'This delivery offer has expired'},
                    status=http_status.HTTP_409_CONFLICT
                )

            if (
                order.delivery_partner_id is not None
                or order.dp_status != 'offered'
                or order.status not in ['accepted', 'preparing']
            ):
                return Response(
                    {'error': 'This order is no longer available for acceptance'},
                    status=http_status.HTTP_409_CONFLICT
                )

            active_delivery_exists = Order.objects.filter(
                delivery_partner=request.user,
                dp_status__in=[
                    'accepted',
                    'arrived_at_shop',
                    'picked_up',
                    'arrived_at_buyer',
                ],
            ).exclude(
                status__in=['cancelled', 'rejected', 'delivered']
            ).exists()

            if active_delivery_exists:
                return Response(
                    {'error': 'Complete your current delivery before accepting another order'},
                    status=http_status.HTTP_409_CONFLICT
                )

            order.delivery_partner = request.user
            order.dp_status = 'accepted'
            order.save(update_fields=[
                'delivery_partner',
                'dp_status',
                'updated_at'
            ])

            offer.status = 'accepted'
            offer.responded_at = timezone.now()
            offer.save(update_fields=['status', 'responded_at'])

        return Response(
            {'message': 'Order accepted', 'order_id': str(order.id)},
            status=http_status.HTTP_200_OK
        )


class DPOrderRejectView(APIView):
    """
    POST /dp/orders/<order_id>/reject/
    Reject the current partner's pending offer and dispatch to the next
    eligible partner.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        if not _is_dp(request):
            return Response(
                {"error": "Not a delivery partner account"},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        from orders.models import DeliveryOffer
        from orders.dispatch_service import create_next_delivery_offer

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist:
                return Response(
                    {"error": "Order not found"},
                    status=http_status.HTTP_404_NOT_FOUND,
                )

            try:
                offer = DeliveryOffer.objects.select_for_update().get(
                    order=order,
                    delivery_partner=request.user,
                    status="pending",
                )
            except DeliveryOffer.DoesNotExist:
                return Response(
                    {"error": "No pending offer found for this order"},
                    status=http_status.HTTP_409_CONFLICT,
                )

            now = timezone.now()

            if offer.expires_at <= now:
                if (
                    order.delivery_partner_id is not None
                    or order.status not in ["accepted", "preparing"]
                    or order.dp_status != "offered"
                ):
                    return Response(
                        {"error": "This order is no longer available for dispatch"},
                        status=http_status.HTTP_409_CONFLICT,
                    )

                offer.status = "expired"
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at"])

                if order.delivery_partner_id is None and order.dp_status == "offered":
                    order.dp_status = "unassigned"
                    order.save(update_fields=["dp_status", "updated_at"])

                expired = True
            else:
                if order.delivery_partner_id is not None:
                    return Response(
                        {"error": "This order has already been assigned"},
                        status=http_status.HTTP_409_CONFLICT,
                    )

                if order.status not in ["accepted", "preparing"] or order.dp_status != "offered":
                    return Response(
                        {"error": "This order is no longer available for dispatch"},
                        status=http_status.HTTP_409_CONFLICT,
                    )

                offer.status = "rejected"
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at"])

                order.dp_status = "unassigned"
                order.save(update_fields=["dp_status", "updated_at"])
                expired = False

        # Dispatch after the current offer has been finalized.
        create_next_delivery_offer(order.id)

        if expired:
            return Response(
                {"error": "Offer expired; the next eligible partner will be considered"},
                status=http_status.HTTP_409_CONFLICT,
            )

        return Response(
            {"message": "Offer rejected; the next eligible partner will be considered"},
            status=http_status.HTTP_200_OK,
        )


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

        raw_otp = request.data.get('otp')
        entered_otp = str(raw_otp).strip() if raw_otp is not None else ''
        if entered_otp != order.delivery_otp:
            return Response({'error': 'Incorrect OTP. Please check with the customer.'}, status=http_status.HTTP_400_BAD_REQUEST)

        order.dp_status = 'delivered'
        order.status = 'delivered'
        order.delivery_otp = None
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