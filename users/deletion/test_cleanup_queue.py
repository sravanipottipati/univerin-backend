from django.test import TestCase

from users.models import User, AccountDeletionRequest
from vendors.models import Vendor
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_queue import (
    queue_account_deletion_assets,
)


class CleanupQueueTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549501",
            password="TestPassword123!",
            full_name="Cleanup Test Vendor",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.user,
            shop_name="Cleanup Test Shop",
            category="supermarket",
            phone_number="9876549501",
            address="Test Street",
            town="Test Town",
            fssai_certificate="fssai_certificates/test.jpg",
        )

        self.deletion_request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="vendor",
            status="pending",
        )

    def test_creates_cleanup_job(self):
        jobs = queue_account_deletion_assets(
            self.deletion_request
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            1,
        )

        job = jobs[0]

        self.assertEqual(job.status, "pending")
        self.assertEqual(job.owner_type, "vendor")
        self.assertEqual(
            job.field_name,
            "fssai_certificate",
        )

    def test_queue_is_idempotent(self):
        queue_account_deletion_assets(
            self.deletion_request
        )

        queue_account_deletion_assets(
            self.deletion_request
        )

        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            1,
        )

    def test_changed_reference_is_rejected(self):
        queue_account_deletion_assets(
            self.deletion_request
        )

        self.vendor.fssai_certificate = (
            "fssai_certificates/different.jpg"
        )
        self.vendor.save()

        with self.assertRaises(ValueError):
            queue_account_deletion_assets(
                self.deletion_request
            )

        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            1,
        )

    def test_invalid_reference_rolls_back(self):
        self.user.profile_photo = (
            "https://example.com/invalid.jpg"
        )
        self.user.save()

        with self.assertRaises(ValueError):
            queue_account_deletion_assets(
                self.deletion_request
            )

        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            0,
        )

    def test_completed_request_cannot_queue_assets(self):
        self.deletion_request.status = "completed"
        self.deletion_request.save()

        with self.assertRaises(ValueError):
            queue_account_deletion_assets(
                self.deletion_request
            )

        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            0,
        )

    def test_wrong_cloudinary_folder_is_rejected(self):
        self.vendor.banner_image = (
            "univerin/dp_documents/pan/document123"
        )
        self.vendor.save()

        with self.assertRaises(ValueError):
            queue_account_deletion_assets(
                self.deletion_request
            )

        self.assertEqual(
            AccountDeletionAsset.objects.count(),
            0,
        )

    def test_valid_cloudinary_banner_is_accepted(self):
        self.vendor.banner_image = (
            "univerin/shop_banners/banner123"
        )
        self.vendor.save()

        jobs = queue_account_deletion_assets(
            self.deletion_request
        )

        self.assertEqual(len(jobs), 2)

        banner_job = next(
            job for job in jobs
            if job.field_name == "banner_image"
        )

        self.assertEqual(
            banner_job.storage_reference,
            "univerin/shop_banners/banner123",
        )
