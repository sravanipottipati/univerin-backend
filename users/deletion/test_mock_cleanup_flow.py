from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_executor import (
    execute_mock_cleanup_and_finalize,
)


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

    def test_failed_cleanup_can_be_retried(self):
        failed = execute_mock_cleanup_and_finalize(
            self.job.pk,
            fail=True,
        )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(self.job.status, "failed")
        self.assertTrue(bool(self.user.profile_photo))

        recovered = execute_mock_cleanup_and_finalize(
            self.job.pk,
            fail=False,
        )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(self.job.status, "completed")
        self.assertEqual(self.job.attempts, 2)
        self.assertFalse(bool(self.user.profile_photo))
