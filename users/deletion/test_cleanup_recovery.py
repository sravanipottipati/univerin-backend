from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job, CleanupClaimError
from users.deletion.cleanup_recovery import inspect_expired_cleanup_jobs


class CleanupRecoveryTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549811",
            password="TestPassword123!",
            full_name="Recovery Test Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/recovery.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]

    def test_expired_processing_job_requires_reconciliation(self):
        claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.job.lease_expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.job.save(update_fields=["lease_expires_at"])

        results = inspect_expired_cleanup_jobs()

        matching = [
            item for item in results
            if item["job_id"] == str(self.job.pk)
        ]

        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["requires_reconciliation"])
        self.assertFalse(matching[0]["automatic_retry_allowed"])

    def test_expired_processing_job_cannot_be_reclaimed(self):
        claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.job.lease_expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.job.save(update_fields=["lease_expires_at"])

        with self.assertRaises(CleanupClaimError):
            claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)

    def test_active_job_not_reported_as_expired(self):
        claim_cleanup_job(self.job.pk)

        results = inspect_expired_cleanup_jobs()

        self.assertNotIn(
            str(self.job.pk),
            [item["job_id"] for item in results],
        )
