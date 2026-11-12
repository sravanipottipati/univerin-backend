from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_executor import (
    execute_mock_cleanup_and_finalize,
    CleanupExecutionError,
)


class MockCleanupGuardTests(TestCase):

    @override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=False)
    def test_mock_cleanup_is_blocked_when_disabled(self):
        user = User.objects.create_user(
            phone_number="9876549901",
            password="TestPassword123!",
            full_name="Guard Test Buyer",
            user_type="buyer",
        )
        user.profile_photo = "profile_photos/guard-test.jpg"
        user.save(update_fields=["profile_photo"])

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        job = queue_account_deletion_assets(request)[0]

        with self.assertRaises(CleanupExecutionError):
            execute_mock_cleanup_and_finalize(job.pk)

        job.refresh_from_db()
        user.refresh_from_db()

        self.assertEqual(job.status, "pending")
        self.assertEqual(job.attempts, 0)
        self.assertEqual(
            user.profile_photo.name,
            "profile_photos/guard-test.jpg",
        )
