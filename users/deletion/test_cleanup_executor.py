from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_executor import execute_cleanup_job
from users.deletion.storage_adapter import FakeStorageAdapter


class CleanupExecutorTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549501",
            password="TestPassword123!",
            full_name="Cleanup Executor Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/executor-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]

    def test_mock_success_requires_finalization(self):
        adapter = FakeStorageAdapter()

        result = execute_cleanup_job(self.job.pk, adapter=adapter)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["requires_finalization"])
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)
        self.assertEqual(len(adapter.deleted_references), 1)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/executor-test.jpg",
        )

    def test_mock_failure_marks_job_failed(self):
        result = execute_cleanup_job(
            self.job.pk,
            adapter=FakeStorageAdapter(fail=True),
        )

        self.job.refresh_from_db()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.attempts, 1)
        self.assertIsNone(self.job.completed_at)

    def test_default_adapter_blocks_deletion(self):
        result = execute_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/executor-test.jpg",
        )
