from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.models import Order
from orders.views import OrderDetailView
from vendors.models import Vendor


class BuyerOTPVisibilityTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9200000001",
            full_name="OTP Buyer",
            user_type="buyer",
        )
        self.other_buyer = User.objects.create_user(
            phone_number="9200000002",
            full_name="Other Buyer",
            user_type="buyer",
        )
        self.seller = User.objects.create_user(
            phone_number="9200000003",
            full_name="OTP Seller",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="OTP Visibility Shop",
            category="grocery",
            phone_number="9200000003",
            address="Test Address",
            town="Test Town",
        )

        self.order = Order.objects.create(
            order_number="UNI-OTP-VIS-001",
            buyer=self.buyer,
            vendor=self.vendor,
            status="dispatched",
            dp_status="picked_up",
            delivery_otp="123456",
            total_amount=Decimal("250.00"),
            delivery_address="Buyer Address",
        )

        self.factory = APIRequestFactory()

    def get_order(self, user):
        request = self.factory.get(
            f"/orders/{self.order.id}/"
        )
        force_authenticate(request, user=user)
        return OrderDetailView.as_view()(
            request, order_id=self.order.id
        )

    def test_buyer_can_see_otp_after_pickup(self):
        response = self.get_order(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["delivery_otp"], "123456")

    def test_buyer_can_see_otp_at_delivery(self):
        self.order.dp_status = "arrived_at_buyer"
        self.order.save(update_fields=["dp_status"])

        response = self.get_order(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["delivery_otp"], "123456")

    def test_buyer_cannot_see_otp_before_pickup(self):
        self.order.dp_status = "arrived_at_shop"
        self.order.save(update_fields=["dp_status"])

        response = self.get_order(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("delivery_otp", response.data)

    def test_seller_cannot_see_otp(self):
        response = self.get_order(self.seller)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("delivery_otp", response.data)

    def test_other_buyer_cannot_access_order(self):
        response = self.get_order(self.other_buyer)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("delivery_otp", response.data)

    def test_otp_hidden_after_delivery(self):
        self.order.dp_status = "delivered"
        self.order.save(update_fields=["dp_status"])

        response = self.get_order(self.buyer)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("delivery_otp", response.data)
