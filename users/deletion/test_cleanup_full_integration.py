from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_executor import execute_cleanup_job
from users.deletion.storage_adapter import FakeStorageAdapter
from users.deletion.storage_verification import FakeStorageVerifier
from users.deletion.reconciliation_verification import verify_cleanup_asset
from users.deletion.reconciliation_service import confirm_cleanup_deletion
from users.deletion.cleanup_finalizer import finalize_verified_cleanup_job
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
)


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class CleanupFullIntegrationTests(TestCase):

    def test_successful_cleanup_verification_confirmation_finalization(self):
        user = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Integration Test Buyer",
            user_type="buyer",
        )
        user.profile_photo = "profile_photos/integration-test.jpg"
        user.save(update_fields=["profile_photo"])

        admin = User.objects.create_user(
            phone_number="9876549702",
            password="TestPassword123!",
            full_name="Integration Test Administrator",
            user_type="buyer",
        )
        admin.is_staff = True
        admin.is_admin = True
        admin.save(update_fields=["is_staff", "is_admin"])

        AccountDeletionReconciliationAccess.objects.create(
            administrator=admin,
            granted_by=admin,
            is_enabled=True,
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )
        job = queue_account_deletion_assets(deletion_request)[0]

        execution = execute_cleanup_job(
            job.pk,
            adapter=FakeStorageAdapter(),
        )
        self.assertTrue(execution["requires_finalization"])

        verification = verify_cleanup_asset(
            job.pk,
            administrator=admin,
            attempt_id=execution["attempt_id"],
            verifier=FakeStorageVerifier(state="absent"),
        )
        self.assertEqual(verification["verification_state"], "absent")

        confirmation = confirm_cleanup_deletion(
            job.pk,
            administrator=admin,
            attempt_id=execution["attempt_id"],
            verification_audit_id=verification["audit_id"],
            explanation="Verified asset absence before finalization.",
        )

        finalized = finalize_verified_cleanup_job(
            job.pk,
            administrator=admin,
            attempt_id=execution["attempt_id"],
            confirmation_audit_id=confirmation.pk,
        )

        user.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(finalized.status, "completed")
        self.assertEqual(job.status, "completed")
        self.assertFalse(bool(user.profile_photo))
        self.assertFalse(user.is_deleted)

        # Complete account erasure only after verified asset cleanup.
        from users.deletion.processor import process_deletion_request

        completed_request = process_deletion_request(
            deletion_request.pk,
            approved_by=admin,
        )

        user.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertEqual(completed_request.status, "completed")
        self.assertEqual(deletion_request.status, "completed")
        self.assertIsNotNone(deletion_request.completed_at)
        self.assertTrue(user.is_deleted)
        self.assertFalse(user.is_active)
