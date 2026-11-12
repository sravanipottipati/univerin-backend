from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.cleanup_finalizer import (
    finalize_cleanup_job,
    CleanupFinalizationError,
)


class CleanupFinalizerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549601",
            password="TestPassword123!",
            full_name="Cleanup Finalizer Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/finalizer-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]

    def test_successful_mock_finalization(self):
        claim_cleanup_job(self.job.pk)

        finalize_cleanup_job(
            self.job.pk,
            storage_result={"result": "ok"},
        )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "completed")
        self.assertIsNotNone(self.job.completed_at)
        self.assertFalse(bool(self.user.profile_photo))
        self.assertFalse(self.user.is_deleted)

    def test_failed_confirmation_is_rejected(self):
        claim_cleanup_job(self.job.pk)

        with self.assertRaises(CleanupFinalizationError):
            finalize_cleanup_job(
                self.job.pk,
                storage_result={"result": "error"},
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))

    def test_changed_reference_blocks_finalization(self):
        claim_cleanup_job(self.job.pk)

        self.user.profile_photo = "profile_photos/changed.jpg"
        self.user.save(update_fields=["profile_photo"])

        with self.assertRaises(CleanupFinalizationError):
            finalize_cleanup_job(
                self.job.pk,
                storage_result={"result": "ok"},
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/changed.jpg",
        )

    def test_pending_job_cannot_be_finalized(self):
        with self.assertRaises(CleanupFinalizationError):
            finalize_cleanup_job(
                self.job.pk,
                storage_result={"result": "ok"},
            )

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending")
