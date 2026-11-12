from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import (
    claim_cleanup_job,
    CleanupClaimError,
)


class JobClaimTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549401",
            password="TestPassword123!",
            full_name="Job Claim Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/claim-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]

    def test_pending_job_can_be_claimed(self):
        claim_cleanup_job(self.job.pk)
        self.job.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)

    def test_processing_job_cannot_be_claimed_twice(self):
        claim_cleanup_job(self.job.pk)

        with self.assertRaises(CleanupClaimError):
            claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.assertEqual(self.job.attempts, 1)

    def test_failed_job_can_be_retried(self):
        self.job.status = "failed"
        self.job.save(update_fields=["status"])

        claim_cleanup_job(self.job.pk)
        self.job.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)

    def test_completed_job_cannot_be_claimed(self):
        self.job.status = "completed"
        self.job.save(update_fields=["status"])

        with self.assertRaises(CleanupClaimError):
            claim_cleanup_job(self.job.pk)

    def test_changed_asset_reference_blocks_claim(self):
        self.user.profile_photo = "profile_photos/changed.jpg"
        self.user.save(update_fields=["profile_photo"])

        with self.assertRaises(Exception):
            claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending")
        self.assertEqual(self.job.attempts, 0)
