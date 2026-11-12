from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request


class AccountDeletionProcessorTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876547777",
            password="TestPassword123!",
            full_name="Deletion Processor Test",
            user_type="buyer",
            email="deletion-test@example.com",
        )

    def make_admin(self):
        return User.objects.create_superuser(
            phone_number="9876549999",
            password="TestPassword123!",
            full_name="Deletion Test Admin",
            user_type="admin",
        )

    def test_request_does_not_erase_personal_data(self):
        result = create_deletion_request(self.user)

        self.user.refresh_from_db()

        self.assertEqual(result["request"].status, "pending")
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(
            self.user.email,
            "deletion-test@example.com",
        )

    def test_processor_must_exist(self):
        from users.deletion.processor import process_deletion_request

        self.assertTrue(callable(process_deletion_request))

    def test_eligible_account_is_deleted_after_admin_approval(self):
        from users.deletion.processor import process_deletion_request

        result = create_deletion_request(self.user)

        # Submitting a request must not immediately delete the account.
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)

        process_deletion_request(
            result["request"].id,
            approved_by=self.make_admin(),
        )

        self.user.refresh_from_db()
        result["request"].refresh_from_db()

        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.is_deleted)
        self.assertIsNotNone(self.user.deleted_at)
        self.assertIsNone(self.user.phone_number)
        self.assertFalse(self.user.email)
        self.assertEqual(result["request"].status, "completed")
        self.assertIsNotNone(result["request"].completed_at)

    def test_blocked_account_cannot_be_deleted(self):
        from unittest.mock import patch
        from users.deletion.processor import (
            process_deletion_request,
            DeletionBlockedError,
        )
        from users.deletion.retention import RetentionAssessment

        result = create_deletion_request(self.user)

        blocked_assessment = RetentionAssessment(
            can_proceed=False,
            account_type="buyer",
            blockers=["Outstanding orders require resolution."],
        )

        with patch(
            "users.deletion.processor.assess_account_deletion",
            return_value=blocked_assessment,
        ):
            with self.assertRaises(DeletionBlockedError):
                process_deletion_request(result["request"].id, approved_by=self.make_admin())

        self.user.refresh_from_db()
        result["request"].refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(result["request"].status, "pending")

    def test_real_pending_order_blocks_deletion(self):
        from decimal import Decimal
        from vendors.models import Vendor
        from orders.models import Order
        from users.deletion.processor import (
            process_deletion_request,
            DeletionBlockedError,
        )

        vendor_user = User.objects.create_user(
            phone_number="9876547788",
            password="TestPassword123!",
            full_name="Test Seller",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Deletion Safety Test Shop",
            category="supermarket",
            phone_number="9876547788",
            address="Test Shop Address",
            town="Test Town",
        )

        order = Order.objects.create(
            buyer=self.user,
            vendor=vendor,
            total_amount=Decimal("250.00"),
            delivery_address="Test Delivery Address",
            status="placed",
            payment_status="pending",
        )

        result = create_deletion_request(self.user)

        self.assertFalse(result["assessment"].can_proceed)

        with self.assertRaises(DeletionBlockedError):
            process_deletion_request(result["request"].id, approved_by=self.make_admin())

        self.user.refresh_from_db()
        result["request"].refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(result["request"].status, "pending")

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(
            Order.objects.get(pk=order.pk).total_amount,
            Decimal("250.00"),
        )

    def test_buyer_personal_data_is_erased_after_processing(self):
        from users.models import Address
        from users.deletion.processor import process_deletion_request

        original_phone = self.user.phone_number

        self.user.fcm_token = "ExponentPushToken[test]"
        self.user.town = "Test Town"
        self.user.save(update_fields=["fcm_token", "town"])

        address = Address.objects.create(
            user=self.user,
            label="Home",
            full_address="123 Test Street",
            town="Test Town",
            state="Andhra Pradesh",
            pincode="500001",
        )

        result = create_deletion_request(self.user)

        process_deletion_request(result["request"].id, approved_by=self.make_admin())

        self.user.refresh_from_db()
        result["request"].refresh_from_db()

        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.is_deleted)
        self.assertIsNotNone(self.user.deleted_at)

        self.assertNotEqual(self.user.phone_number, original_phone)
        self.assertNotEqual(
            self.user.full_name,
            "Deletion Processor Test",
        )

        self.assertFalse(self.user.email)
        self.assertFalse(self.user.fcm_token)
        self.assertFalse(self.user.town)

        self.assertFalse(
            Address.objects.filter(pk=address.pk).exists()
        )

        self.assertEqual(result["request"].status, "completed")
        self.assertIsNotNone(result["request"].completed_at)

    def test_unconfirmed_razorpay_checkout_blocks_deletion(self):
        from decimal import Decimal
        from vendors.models import Vendor
        from orders.models import RazorpayCheckout
        from users.deletion.processor import (
            process_deletion_request,
            DeletionBlockedError,
        )

        vendor_user = User.objects.create_user(
            phone_number="9876547799",
            password="TestPassword123!",
            full_name="Checkout Test Seller",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Checkout Safety Shop",
            category="supermarket",
            phone_number="9876547799",
            address="Test Shop Address",
            town="Test Town",
        )

        checkout = RazorpayCheckout.objects.create(
            buyer=self.user,
            vendor=vendor,
            amount_paise=25000,
            status="created",
            snapshot={
                "vendor_id": str(vendor.pk),
                "delivery_address": "123 Private Street",
                "delivery_latitude": 17.385,
                "delivery_longitude": 78.4867,
                "items": [],
                "total": str(Decimal("250.00")),
            },
        )

        result = create_deletion_request(self.user)

        self.assertFalse(result["assessment"].can_proceed)
        self.assertIn(
            "Unconfirmed Razorpay checkouts require resolution.",
            result["assessment"].blockers,
        )

        with self.assertRaises(DeletionBlockedError):
            process_deletion_request(result["request"].id, approved_by=self.make_admin())

        self.user.refresh_from_db()
        result["request"].refresh_from_db()
        checkout.refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(result["request"].status, "pending")
        self.assertEqual(checkout.status, "created")
        self.assertEqual(
            checkout.snapshot["delivery_address"],
            "123 Private Street",
        )

    def test_return_request_blocks_buyer_deletion(self):
        from decimal import Decimal
        from vendors.models import Vendor
        from orders.models import Order, ReturnRequest

        vendor_user = User.objects.create_user(
            phone_number="9876547766",
            password="TestPassword123!",
            full_name="Return Test Seller",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Return Safety Shop",
            category="supermarket",
            phone_number="9876547766",
            address="Test Shop Address",
            town="Test Town",
        )

        order = Order.objects.create(
            buyer=self.user,
            vendor=vendor,
            total_amount=Decimal("250.00"),
            delivery_address="Test Delivery Address",
            status="delivered",
            payment_status="paid",
        )

        ReturnRequest.objects.create(
            order=order,
            buyer=self.user,
            reason="Damaged item",
            comment="Return awaiting review",
        )

        result = create_deletion_request(self.user)

        self.assertFalse(
            result["assessment"].can_proceed,
            "An unresolved return request must block deletion.",
        )

        self.assertTrue(
            any(
                "return" in blocker.lower()
                for blocker in result["assessment"].blockers
            )
        )
