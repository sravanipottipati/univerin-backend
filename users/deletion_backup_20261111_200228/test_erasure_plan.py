from decimal import Decimal

from django.test import TestCase

from users.models import User, Address
from vendors.models import Vendor
from orders.models import Order
from users.deletion.erasure_plan import build_buyer_erasure_plan


class BuyerErasurePlanTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876547701",
            password="TestPassword123!",
            full_name="Erasure Plan Buyer",
            user_type="buyer",
        )

    def test_buyer_without_transactions(self):
        Address.objects.create(
            user=self.buyer,
            label="Home",
            full_address="123 Test Street",
            town="Test Town",
            state="Andhra Pradesh",
            pincode="500001",
        )

        plan = build_buyer_erasure_plan(self.buyer)

        self.assertEqual(plan["saved_addresses_to_delete"], 1)
        self.assertEqual(plan["historical_orders_to_preserve"], 0)
        self.assertEqual(plan["checkout_snapshots_to_review"], 0)
        self.assertFalse(plan["requires_retention_review"])
        self.assertFalse(plan["ready_for_automatic_erasure"])

        # Planning must never modify the account or address.
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.is_active)
        self.assertEqual(
            Address.objects.filter(user=self.buyer).count(),
            1,
        )

    def test_historical_order_requires_review(self):
        vendor_user = User.objects.create_user(
            phone_number="9876547702",
            password="TestPassword123!",
            full_name="Erasure Plan Vendor",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Erasure Test Shop",
            category="supermarket",
            phone_number="9876547702",
            address="Test Shop Address",
            town="Test Town",
        )

        order = Order.objects.create(
            buyer=self.buyer,
            vendor=vendor,
            total_amount=Decimal("250.00"),
            delivery_address="123 Private Street",
            delivery_latitude=17.385,
            delivery_longitude=78.4867,
            status="delivered",
            payment_status="paid",
        )

        plan = build_buyer_erasure_plan(self.buyer)

        self.assertEqual(plan["historical_orders_to_preserve"], 1)
        self.assertEqual(
            plan["orders_with_delivery_addresses_to_review"],
            1,
        )
        self.assertEqual(
            plan["orders_with_coordinates_to_review"],
            1,
        )
        self.assertTrue(plan["requires_retention_review"])
        self.assertFalse(plan["ready_for_automatic_erasure"])

        # The original order and its financial data must remain intact.
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("250.00"))
        self.assertEqual(
            order.delivery_address,
            "123 Private Street",
        )

    def test_additional_personal_data_counts(self):
        from datetime import timedelta
        from django.utils import timezone
        from users.models import PasswordResetOTP

        address = Address.objects.create(
            user=self.buyer,
            label="Home",
            full_address="456 Private Street",
            town="Test Town",
            state="Andhra Pradesh",
            pincode="500001",
        )

        otp = PasswordResetOTP.objects.create(
            user=self.buyer,
            otp="123456",
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        plan = build_buyer_erasure_plan(self.buyer)

        self.assertEqual(plan["saved_addresses_to_delete"], 1)
        self.assertEqual(plan["password_reset_otps_to_delete"], 1)

        self.assertEqual(plan["cart_items_to_delete"], 0)
        self.assertEqual(plan["wishlist_items_to_delete"], 0)
        self.assertEqual(plan["notifications_to_review"], 0)
        self.assertEqual(plan["reviews_to_review"], 0)
        self.assertEqual(plan["refunds_to_review"], 0)
        self.assertEqual(plan["return_requests_to_review"], 0)

        # The planner must remain read-only.
        self.assertTrue(Address.objects.filter(pk=address.pk).exists())
        self.assertTrue(
            PasswordResetOTP.objects.filter(pk=otp.pk).exists()
        )

        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
