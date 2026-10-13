from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from orders.admin import OrderAdmin
from orders.models import Order
from orders.test_delivery_otp import DeliveryOTPTests


class DeliveryOTPAdminTests(DeliveryOTPTests):
    def setUp(self):
        super().setUp()

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            phone_number="9100000005",
            full_name="OTP Admin",
            password="test-password-123",
        )

        self.staff = User.objects.create_user(
            phone_number="9100000006",
            full_name="OTP Staff",
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])

        self.order_admin = OrderAdmin(Order, admin.site)
        self.request_factory = RequestFactory()

    def admin_request(self, user):
        request = self.request_factory.post("/admin/orders/order/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request


    def test_delivery_otp_fields_are_readonly(self):
        request = self.admin_request(self.superuser)
        readonly_fields = self.order_admin.get_readonly_fields(
            request, self.order
        )

        self.assertIn("delivery_otp", readonly_fields)
        self.assertIn("delivery_otp_attempts", readonly_fields)
        self.assertIn("status", readonly_fields)
        self.assertIn("dp_status", readonly_fields)

    def test_staff_cannot_access_reset_action(self):
        request = self.admin_request(self.staff)
        actions = self.order_admin.get_actions(request)
        self.assertNotIn("reset_locked_delivery_otp", actions)

    def test_superuser_can_access_reset_action(self):
        request = self.admin_request(self.superuser)
        actions = self.order_admin.get_actions(request)
        self.assertIn("reset_locked_delivery_otp", actions)

    def test_superuser_resets_locked_otp(self):
        self.order.delivery_otp_attempts = 5
        self.order.save(update_fields=["delivery_otp_attempts"])

        request = self.admin_request(self.superuser)

        with patch("secrets.randbelow", return_value=554321):
            self.order_admin.reset_locked_delivery_otp(
                request, Order.objects.filter(pk=self.order.pk)
            )

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp, "654321")
        self.assertEqual(self.order.delivery_otp_attempts, 0)
        self.assertEqual(self.order.dp_status, "arrived_at_buyer")

    def test_unlocked_order_is_not_reset(self):
        request = self.admin_request(self.superuser)

        self.order_admin.reset_locked_delivery_otp(
            request, Order.objects.filter(pk=self.order.pk)
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp, "123456")
        self.assertEqual(self.order.delivery_otp_attempts, 0)

    def test_staff_cannot_reset_even_if_action_called_directly(self):
        self.order.delivery_otp_attempts = 5
        self.order.save(update_fields=["delivery_otp_attempts"])

        request = self.admin_request(self.staff)

        self.order_admin.reset_locked_delivery_otp(
            request, Order.objects.filter(pk=self.order.pk)
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_otp, "123456")
        self.assertEqual(self.order.delivery_otp_attempts, 5)
