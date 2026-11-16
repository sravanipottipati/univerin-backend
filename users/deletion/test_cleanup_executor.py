from unittest.mock import patch

from django.test import TestCase

from users.models import User, AccountDeletionRequest

from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job
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

        self.user.profile_photo = (
            "profile_photos/executor-test.jpg"
        )
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(
            self.request
        )[0]

    def test_mock_success_requires_finalization(self):
        adapter = FakeStorageAdapter()

        result = execute_cleanup_job(
            self.job.pk,
            adapter=adapter,
        )

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

    def test_mock_failure_requires_reconciliation(self):
        adapter = FakeStorageAdapter(fail=True)

        result = execute_cleanup_job(
            self.job.pk,
            adapter=adapter,
        )

        self.job.refresh_from_db()

        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["requires_reconciliation"])
        self.assertFalse(result["automatic_retry_allowed"])
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)
        self.assertIsNone(self.job.completed_at)

    def test_default_adapter_blocks_real_deletion(self):
        result = execute_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(result["status"], "processing")
        self.assertTrue(result["requires_reconciliation"])

        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/executor-test.jpg",
        )

    def test_changed_reference_after_claim_blocks_adapter(self):
        adapter = FakeStorageAdapter()

        from users.deletion.cleanup_executor import claim_cleanup_job

        original_claim = claim_cleanup_job

        def claim_then_replace(job_id):
            job = original_claim(job_id)

            User.objects.filter(
                pk=self.user.pk
            ).update(
                profile_photo="profile_photos/replacement.jpg"
            )

            return job

        with patch(
            "users.deletion.cleanup_executor.claim_cleanup_job",
            side_effect=claim_then_replace,
        ):
            result = execute_cleanup_job(
                self.job.pk,
                adapter=adapter,
            )

        self.job.refresh_from_db()

        self.assertTrue(result["requires_reconciliation"])
        self.assertFalse(result["automatic_retry_allowed"])
        self.assertEqual(adapter.deleted_references, [])
        self.assertEqual(self.job.status, "processing")
        self.assertIn("validation failed", self.job.last_error)

    def test_shared_reference_after_claim_blocks_adapter(self):
        adapter = FakeStorageAdapter()

        other = User.objects.create_user(
            phone_number="9876549502",
            password="TestPassword123!",
            full_name="Second Asset Owner",
            user_type="buyer",
        )

        original_claim = claim_cleanup_job

        def claim_then_share(job_id):
            job = original_claim(job_id)

            User.objects.filter(
                pk=other.pk
            ).update(
                profile_photo="profile_photos/executor-test.jpg"
            )

            return job

        with patch(
            "users.deletion.cleanup_executor.claim_cleanup_job",
            side_effect=claim_then_share,
        ):
            result = execute_cleanup_job(
                self.job.pk,
                adapter=adapter,
            )

        self.job.refresh_from_db()

        self.assertTrue(result["requires_reconciliation"])
        self.assertEqual(adapter.deleted_references, [])
        self.assertEqual(self.job.status, "processing")
        self.assertIn("validation failed", self.job.last_error)
