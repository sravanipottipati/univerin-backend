from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_executor import (
    execute_mock_cleanup_and_finalize,
)


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class MockCleanupFlowTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549801",
            password="TestPassword123!",
            full_name="Mock Cleanup Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/mock-flow.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )
        self.job = queue_account_deletion_assets(self.request)[0]

    def test_successful_mock_cleanup(self):
        result = execute_mock_cleanup_and_finalize(self.job.pk)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["mock_only"])
        self.assertFalse(result["external_deletion_performed"])
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.attempts, 1)
        self.assertFalse(bool(self.user.profile_photo))
        self.assertFalse(self.user.is_deleted)

    def test_uncertain_cleanup_cannot_be_retried(self):
        failed = execute_mock_cleanup_and_finalize(
            self.job.pk,
            fail=True,
        )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(failed["status"], "processing")
        self.assertTrue(failed["requires_reconciliation"])
        self.assertFalse(failed["automatic_retry_allowed"])
        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))

        from users.deletion.job_claim import CleanupClaimError

        with self.assertRaises(CleanupClaimError):
            execute_mock_cleanup_and_finalize(
                self.job.pk,
                fail=False,
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)
        self.assertTrue(bool(self.user.profile_photo))
