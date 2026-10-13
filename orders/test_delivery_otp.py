from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.models import Order
from orders.dp_views import DPOrderStatusUpdateView, DPVerifyDeliveryOTPView
from vendors.models import Vendor


class DeliveryOTPTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9100000001",
            full_name="OTP Test Buyer",
            user_type="buyer",
        )
        seller = User.objects.create_user(
            phone_number="9100000002",
            full_name="OTP Test Seller",
            user_type="vendor",
        )
        self.dp = User.objects.create_user(
            phone_number="9100000003",
            full_name="OTP Test DP",
            user_type="delivery_partner",
        )
        self.other_dp = User.objects.create_user(
            phone_number="9100000004",
            full_name="Other DP",
            user_type="delivery_partner",
        )

        vendor = Vendor.objects.create(
            user=seller,
            shop_name="OTP Test Shop",
            category="grocery",
            phone_number="9100000002",
            address="Test Address",
            town="Test Town",
        )

        self.order = Order.objects.create(
            order_number="UNI-OTP-001",
            buyer=self.buyer,
            vendor=vendor,
            delivery_partner=self.dp,
            status="dispatched",
            dp_status="arrived_at_buyer",
            delivery_otp="123456",
            total_amount=Decimal("250.00"),
            delivery_address="Buyer Address",
        )

        self.factory = APIRequestFactory()

    def verify(self, otp, user=None):
        request = self.factory.post(
            f"/dp/orders/{self.order.id}/verify-delivery-otp/",
            {"otp": otp},
            format="json",
        )
        force_authenticate(request, user=user or self.dp)
        return DPVerifyDeliveryOTPView.as_view()(
            request, order_id=self.order.id
        )

    def test_correct_otp_confirms_delivery(self):
        response = self.verify("123456")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "delivered")
        self.assertEqual(self.order.status, "delivered")
        self.assertIsNone(self.order.delivery_otp)

    def test_numeric_otp_confirms_delivery(self):
        response = self.verify(123456)
        self.assertEqual(response.status_code, 200)

    def test_incorrect_otp_is_rejected(self):
        response = self.verify("999999")
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "arrived_at_buyer")

    def test_missing_otp_is_rejected(self):
        response = self.verify(None)
        self.assertEqual(response.status_code, 400)

    def test_other_partner_cannot_verify(self):
        response = self.verify("123456", user=self.other_dp)
        self.assertEqual(response.status_code, 404)

    def test_otp_cannot_be_reused_after_delivery(self):
        self.assertEqual(self.verify("123456").status_code, 200)
        self.assertEqual(self.verify("123456").status_code, 400)

    def test_otp_generated_on_pickup(self):
        self.order.dp_status = "arrived_at_shop"
        self.order.delivery_otp = None
        self.order.status = "preparing"
        self.order.save()

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/status/",
            {"dp_status": "picked_up"},
            format="json",
        )
        force_authenticate(request, user=self.dp)

        with patch("orders.dp_views.secrets.randbelow", return_value=554321):
            response = DPOrderStatusUpdateView.as_view()(
                request, order_id=self.order.id
            )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp, "654321")
        self.assertEqual(self.order.dp_status, "picked_up")
        self.assertEqual(self.order.status, "dispatched")


    def test_duplicate_pickup_does_not_regenerate_otp(self):
        self.order.dp_status = "arrived_at_shop"
        self.order.delivery_otp = None
        self.order.status = "preparing"
        self.order.save()

        def pickup():
            request = self.factory.post(
                f"/dp/orders/{self.order.id}/status/",
                {"dp_status": "picked_up"},
                format="json",
            )
            force_authenticate(request, user=self.dp)
            return DPOrderStatusUpdateView.as_view()(
                request, order_id=self.order.id
            )

        with patch("orders.dp_views.secrets.randbelow", return_value=111111):
            first_response = pickup()

        self.assertEqual(first_response.status_code, 200)

        self.order.refresh_from_db()
        original_otp = self.order.delivery_otp

        with patch("orders.dp_views.secrets.randbelow") as generate_otp:
            second_response = pickup()

        self.assertEqual(second_response.status_code, 400)
        generate_otp.assert_not_called()

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp, original_otp)
        self.assertEqual(self.order.dp_status, "picked_up")

    def test_otp_locked_after_five_incorrect_attempts(self):
        for attempt in range(5):
            response = self.verify("999999")
            self.assertEqual(response.status_code, 400)

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp_attempts, 5)
        self.assertEqual(self.order.dp_status, "arrived_at_buyer")

        response = self.verify("123456")
        self.assertEqual(response.status_code, 429)

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "arrived_at_buyer")
        self.assertEqual(self.order.status, "dispatched")
