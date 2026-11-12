from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request
from users.deletion.worker_erasure import WorkerErasureNotReadyError
from users.deletion.processor import (
    process_deletion_request,
    DeletionNotImplementedError,
    DeletionBlockedError,
)


class WorkerDeletionProtectionTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="9876549900",
            password="TestPassword123!",
            full_name="Deletion Test Admin",
            user_type="admin",
        )

    def test_vendor_without_profile_cannot_be_deleted(self):
        vendor_user = User.objects.create_user(
            phone_number="9876549901",
            password="TestPassword123!",
            full_name="Test Vendor",
            user_type="vendor",
        )

        request = create_deletion_request(vendor_user)["request"]

        with self.assertRaises(DeletionBlockedError):
            process_deletion_request(
                request.pk,
                approved_by=self.admin,
            )

        vendor_user.refresh_from_db()
        request.refresh_from_db()

        self.assertTrue(vendor_user.is_active)
        self.assertFalse(vendor_user.is_deleted)
        self.assertEqual(request.status, "pending")

    def test_delivery_partner_without_profile_cannot_be_deleted(self):
        partner_user = User.objects.create_user(
            phone_number="9876549902",
            password="TestPassword123!",
            full_name="Test Delivery Partner",
            user_type="delivery_partner",
        )

        request = create_deletion_request(partner_user)["request"]

        with self.assertRaises(WorkerErasureNotReadyError):
            process_deletion_request(
                request.pk,
                approved_by=self.admin,
            )

        partner_user.refresh_from_db()
        request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(request.status, "pending")
