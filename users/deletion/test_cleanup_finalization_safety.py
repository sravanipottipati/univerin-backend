from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request
from users.deletion.cleanup_models import AccountDeletionAsset


class CleanupFinalizationSafetyTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876549201",
            password="TestPassword123!",
            full_name="Buyer With Uploaded Photo",
            user_type="buyer",
        )
        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        self.admin = User.objects.create_superuser(
            phone_number="9876549202",
            password="TestPassword123!",
            full_name="Deletion Administrator",
            user_type="admin",
        )

        self.request = create_deletion_request(self.buyer)["request"]

        process_deletion_request(
            self.request.pk,
            approved_by=self.admin,
        )

    def test_completed_job_with_existing_photo_does_not_erase_account(self):
        job = AccountDeletionAsset.objects.get(
            deletion_request=self.request
        )
        job.status = "completed"
        job.save(update_fields=["status"])

        process_deletion_request(
            self.request.pk,
            approved_by=self.admin,
        )

        self.buyer.refresh_from_db()
        self.request.refresh_from_db()

        self.assertFalse(self.buyer.is_deleted)
        self.assertTrue(self.buyer.is_active)
        self.assertEqual(self.request.status, "pending")

    def test_pending_job_does_not_erase_account(self):
        process_deletion_request(
            self.request.pk,
            approved_by=self.admin,
        )

        self.buyer.refresh_from_db()
        self.request.refresh_from_db()

        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(self.request.status, "pending")
