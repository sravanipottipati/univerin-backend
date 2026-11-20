from unittest.mock import patch

from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest

from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.cleanup_executor import execute_cleanup_job
from users.deletion.storage_adapter import FakeStorageAdapter


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
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

    def test_success_immediately_allows_independent_verification(self):
        from django.utils import timezone
        from users.deletion.reconciliation_verification import (
            _validate_job,
        )

        result = execute_cleanup_job(
            self.job.pk,
            adapter=FakeStorageAdapter(),
        )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertTrue(result["requires_finalization"])
        self.assertEqual(self.job.status, "processing")
        self.assertIsNotNone(self.job.lease_expires_at)
        self.assertLessEqual(
            self.job.lease_expires_at,
            timezone.now(),
        )

        # Verification eligibility must not require a manual
        # lease update after successful storage execution.
        _validate_job(self.job, self.job.attempt_id)

        # Verification/finalization have not yet happened.
        self.assertIsNone(self.job.completed_at)
        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/executor-test.jpg",
        )
        self.assertFalse(self.user.is_deleted)

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

    def test_unauthorized_real_adapter_does_not_claim_job(self):
        from django.test import override_settings
        from users.deletion.cleanup_executor import CleanupExecutionError
        from users.deletion.storage_adapter import CloudinaryStorageAdapter

        with override_settings(
            ACCOUNT_DELETION_AUTOMATIC_ENABLED=False,
            ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED=False,
        ):
            with patch.object(
                CloudinaryStorageAdapter,
                "delete",
            ) as mock_delete:
                with self.assertRaisesRegex(
                    CleanupExecutionError,
                    "Production storage deletion is not authorized",
                ):
                    execute_cleanup_job(
                        self.job.pk,
                        adapter=CloudinaryStorageAdapter(),
                    )

                mock_delete.assert_not_called()

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending")
        self.assertEqual(self.job.attempts, 0)

    def test_fake_adapter_disabled_outside_tests(self):
        from django.test import override_settings
        from users.deletion.cleanup_executor import CleanupExecutionError

        adapter = FakeStorageAdapter()

        with override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=False):
            with self.assertRaisesRegex(
                CleanupExecutionError,
                "Fake cleanup is restricted",
            ):
                execute_cleanup_job(self.job.pk, adapter=adapter)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending")
        self.assertEqual(self.job.attempts, 0)
        self.assertEqual(adapter.deleted_references, [])

    def test_unapproved_adapter_is_rejected(self):
        from users.deletion.cleanup_executor import CleanupExecutionError

        class UnapprovedAdapter:
            def delete(self, *args, **kwargs):
                raise AssertionError("Unapproved adapter was called.")

        with self.assertRaisesRegex(
            CleanupExecutionError,
            "Unapproved storage cleanup adapter",
        ):
            execute_cleanup_job(
                self.job.pk,
                adapter=UnapprovedAdapter(),
            )

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "pending")
        self.assertEqual(self.job.attempts, 0)

    def test_real_adapter_rejected_on_test_database(self):
        from django.test import override_settings
        from users.deletion.cleanup_executor import CleanupExecutionError
        from users.deletion.storage_adapter import CloudinaryStorageAdapter

        with override_settings(
            ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
            ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED=True,
            ACCOUNT_DELETION_RAILWAY_ENVIRONMENT="production",
            DEBUG=False,
        ):
            with patch.object(
                CloudinaryStorageAdapter,
                "delete",
            ) as mock_delete:
                with self.assertRaises(CleanupExecutionError):
                    execute_cleanup_job(
                        self.job.pk,
                        adapter=CloudinaryStorageAdapter(),
                    )

                mock_delete.assert_not_called()

        self.job.refresh_from_db()

        self.assertEqual(self.job.status, "pending")
        self.assertEqual(self.job.attempts, 0)
