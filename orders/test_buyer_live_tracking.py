from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from delivery_partner.models import DeliveryPartner
from orders.models import Order
from orders.views import BuyerDeliveryTrackingView
from vendors.models import Vendor


class BuyerLiveTrackingTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9300000001",
            full_name="Tracking Buyer",
            user_type="buyer",
        )
        self.other_buyer = User.objects.create_user(
            phone_number="9300000002",
            full_name="Other Tracking Buyer",
            user_type="buyer",
        )
        self.seller = User.objects.create_user(
            phone_number="9300000003",
            full_name="Tracking Seller",
            user_type="vendor",
        )
        self.dp_user = User.objects.create_user(
            phone_number="9300000004",
            full_name="Tracking Delivery Partner",
            user_type="delivery_partner",
        )

        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="Tracking Test Shop",
            category="grocery",
            phone_number="9300000003",
            address="Test Address",
            town="Test Town",
        )

        self.dp = DeliveryPartner.objects.create(
            user=self.dp_user,
            status="approved",
            is_online=True,
            current_latitude=17.4123,
            current_longitude=78.4567,
            location_updated_at=timezone.now(),
        )

        self.order = Order.objects.create(
            order_number="UNI-TRACK-001",
            buyer=self.buyer,
            vendor=self.vendor,
            status="dispatched",
            dp_status="picked_up",
            delivery_partner=self.dp_user,
            total_amount=Decimal("250.00"),
            delivery_address="Tracking Buyer Address",
        )

        self.factory = APIRequestFactory()

    def track(self, user=None):
        request = self.factory.get(
            f"/orders/{self.order.id}/tracking/"
        )
        if user is not None:
            force_authenticate(request, user=user)

        return BuyerDeliveryTrackingView.as_view()(
            request, order_id=self.order.id
        )

    def test_unauthenticated_user_rejected(self):
        response = self.track()
        self.assertIn(response.status_code, (401, 403))

    def test_other_buyer_cannot_track(self):
        response = self.track(self.other_buyer)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("latitude", response.data)

    def test_seller_cannot_track(self):
        response = self.track(self.seller)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("latitude", response.data)

    def test_buyer_can_track_fresh_location(self):
        response = self.track(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["tracking_available"])
        self.assertEqual(response.data["latitude"], 17.4123)
        self.assertEqual(response.data["longitude"], 78.4567)
        self.assertEqual(response.data["dp_status"], "picked_up")

    def test_stale_location_hidden(self):
        self.dp.location_updated_at = (
            timezone.now() - timedelta(minutes=5)
        )
        self.dp.save(update_fields=["location_updated_at"])

        response = self.track(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["tracking_available"])
        self.assertNotIn("latitude", response.data)

    def test_delivered_order_hidden(self):
        self.order.status = "delivered"
        self.order.dp_status = "delivered"
        self.order.save(update_fields=["status", "dp_status"])

        response = self.track(self.buyer)
        self.assertFalse(response.data["tracking_available"])
        self.assertNotIn("latitude", response.data)

    def test_cancelled_order_hidden(self):
        self.order.status = "cancelled"
        self.order.save(update_fields=["status"])

        response = self.track(self.buyer)
        self.assertFalse(response.data["tracking_available"])
        self.assertNotIn("latitude", response.data)

    def test_unassigned_order_hidden(self):
        self.order.delivery_partner = None
        self.order.dp_status = "unassigned"
        self.order.save(update_fields=["delivery_partner", "dp_status"])

        response = self.track(self.buyer)
        self.assertFalse(response.data["tracking_available"])
        self.assertNotIn("latitude", response.data)
