from django.test import TestCase

from users.models import User, AccountDeletionRequest
from vendors.models import Vendor
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_worker import (
    inspect_cleanup_job,
    AssetCleanupBlockedError,
)


class CleanupWorkerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Cleanup Worker Vendor",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.user,
            shop_name="Worker Test Shop",
            category="supermarket",
            phone_number="9876549701",
            address="Test Street",
            town="Test Town",
            fssai_certificate="fssai_certificates/test.jpg",
        )

        self.deletion_request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="vendor",
            status="pending",
        )

        self.job = queue_account_deletion_assets(
            self.deletion_request
        )[0]

    def test_valid_job_passes_dry_run(self):
        result = inspect_cleanup_job(self.job.pk)

        self.assertTrue(result["reference_verified"])
        self.assertFalse(result["ready_for_external_cleanup"])

    def test_changed_reference_is_blocked(self):
        self.vendor.fssai_certificate = (
            "fssai_certificates/replacement.jpg"
        )
        self.vendor.save()

        with self.assertRaises(AssetCleanupBlockedError):
            inspect_cleanup_job(self.job.pk)

    def test_completed_job_is_blocked(self):
        self.job.status = "completed"
        self.job.save(update_fields=["status"])

        with self.assertRaises(AssetCleanupBlockedError):
            inspect_cleanup_job(self.job.pk)

    def test_account_type_mismatch_is_blocked(self):
        self.deletion_request.account_type = "buyer"
        self.deletion_request.save(update_fields=["account_type"])

        with self.assertRaises(AssetCleanupBlockedError):
            inspect_cleanup_job(self.job.pk)
