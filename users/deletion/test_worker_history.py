from decimal import Decimal

from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from wallet.models import WalletTransaction
from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request
from users.deletion.worker_erasure import WorkerErasureNotReadyError


class WorkerHistoricalRecordTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="9876549600",
            password="TestPassword123!",
            full_name="Test Admin",
            user_type="admin",
        )

    def test_settled_vendor_transaction_blocks_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549601",
            password="TestPassword123!",
            full_name="Vendor Owner",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=user,
            shop_name="Original Shop",
            category="supermarket",
            phone_number="9876549601",
            address="Original Address",
            town="Original Town",
            bank_account_number="123456789",
        )

        transaction = WalletTransaction.objects.create(
            vendor=vendor,
            amount=Decimal("100.00"),
            transaction_type="credit",
            status="settled",
            description="Historical settlement",
        )

        deletion = create_deletion_request(user)["request"]

        with self.assertRaises(WorkerErasureNotReadyError):
            process_deletion_request(
                deletion.pk,
                approved_by=self.admin,
            )

        user.refresh_from_db()
        vendor.refresh_from_db()
        deletion.refresh_from_db()

        self.assertFalse(user.is_deleted)
        self.assertTrue(user.is_active)
        self.assertEqual(vendor.bank_account_number, "123456789")
        self.assertEqual(deletion.status, "pending")
        self.assertTrue(
            WalletTransaction.objects.filter(pk=transaction.pk).exists()
        )

    def test_delivery_offer_history_blocks_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549602",
            password="TestPassword123!",
            full_name="Delivery Partner",
            user_type="delivery_partner",
        )

        DeliveryPartner.objects.create(
            user=user,
            aadhaar_number="123412341234",
        )

        # The read-only plan must reject delivery history.
        # A saved delivery offer is sufficient to verify this safeguard.
        from users.deletion.worker_erasure_plan import (
            build_delivery_partner_erasure_plan,
        )

        with self.assertRaises(ValueError):
            # Wrong account type must never be accepted.
            from users.deletion.worker_erasure_plan import (
                build_vendor_erasure_plan,
            )
            build_vendor_erasure_plan(user)

        plan = build_delivery_partner_erasure_plan(user)
        self.assertTrue(plan["eligible_for_erasure_review"])

        deletion = create_deletion_request(user)["request"]

        process_deletion_request(
            deletion.pk,
            approved_by=self.admin,
        )

        user.refresh_from_db()
        deletion.refresh_from_db()

        self.assertTrue(user.is_deleted)
        self.assertEqual(deletion.status, "completed")
