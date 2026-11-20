import uuid

from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.cleanup_finalizer import (
    finalize_verified_cleanup_job,
    CleanupFinalizationError,
)


class VerifiedFinalizerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549691",
            password="TestPassword123!",
            full_name="Verified Finalizer Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/verified-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]
        self.claimed = claim_cleanup_job(self.job.pk)

    def test_missing_administrator_is_rejected(self):
        with self.assertRaises(Exception):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=None,
                attempt_id=self.claimed.attempt_id,
                confirmation_audit_id=uuid.uuid4(),
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))

    def test_invalid_attempt_id_is_rejected(self):
        with self.assertRaises(CleanupFinalizationError):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=None,
                attempt_id="invalid",
                confirmation_audit_id=uuid.uuid4(),
            )

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")

    def test_missing_confirmation_is_rejected(self):
        with self.assertRaises(Exception):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=None,
                attempt_id=self.claimed.attempt_id,
                confirmation_audit_id=uuid.uuid4(),
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))

    def test_authorized_admin_without_confirmation_is_rejected(self):
        from users.deletion.reconciliation_models import (
            AccountDeletionReconciliationAccess,
        )

        admin = User.objects.create_user(
            phone_number="9876549692",
            password="TestPassword123!",
            full_name="Deletion Administrator",
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

        with self.assertRaisesRegex(
            CleanupFinalizationError,
            "Explicit deletion confirmation is required",
        ):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=admin,
                attempt_id=self.claimed.attempt_id,
                confirmation_audit_id=uuid.uuid4(),
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))

    def test_valid_confirmation_completes_cleanup(self):
        from users.deletion.reconciliation_models import (
            AccountDeletionReconciliationAccess,
            AccountDeletionReconciliationAudit,
        )

        admin = User.objects.create_user(
            phone_number="9876549693",
            password="TestPassword123!",
            full_name="Authorized Cleanup Admin",
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

        from django.utils import timezone
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
        )

        # Simulate an uncertain cleanup attempt requiring reconciliation.
        self.job.lease_expires_at = timezone.now()
        self.job.save(update_fields=["lease_expires_at"])

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.claimed.attempt_id,
            administrator=admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            verified_storage_reference="profile_photos/verified-test.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            evidence_reference="cloudinary:test-asset-absent",
            explanation="Simulated read-only absence verification.",
        )

        confirmation = confirm_cleanup_deletion(
            self.job.pk,
            administrator=admin,
            attempt_id=self.claimed.attempt_id,
            verification_audit_id=verification.pk,
            explanation="Administrator reviewed the verified absence evidence.",
        )

        finalized = finalize_verified_cleanup_job(
            self.job.pk,
            administrator=admin,
            attempt_id=self.claimed.attempt_id,
            confirmation_audit_id=confirmation.pk,
        )

        self.user.refresh_from_db()
        self.job.refresh_from_db()

        self.assertEqual(finalized.status, "completed")
        self.assertEqual(self.job.status, "completed")
        self.assertFalse(bool(self.user.profile_photo))
        self.assertFalse(self.user.is_deleted)

    def test_confirmation_without_verification_is_rejected(self):
        from users.deletion.reconciliation_models import (
            AccountDeletionReconciliationAccess,
            AccountDeletionReconciliationAudit,
        )

        admin = User.objects.create_user(
            phone_number="9876549694",
            password="TestPassword123!",
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

        confirmation = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.claimed.attempt_id,
            administrator=admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .DELETION_CONFIRMED
            ),
            evidence_reference="unverified-confirmation",
            explanation="Confirmation without verified absence evidence.",
        )

        with self.assertRaises(CleanupFinalizationError):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=admin,
                attempt_id=self.claimed.attempt_id,
                confirmation_audit_id=confirmation.pk,
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))


    def test_finalizer_rejects_mismatched_asset_evidence(self):
        from users.deletion.reconciliation_models import (
            AccountDeletionReconciliationAccess,
            AccountDeletionReconciliationAudit,
        )

        admin = User.objects.create_user(
            phone_number="9876549695",
            password="TestPassword123!",
            full_name="Mismatch Evidence Administrator",
            user_type="buyer",
            is_staff=True,
            is_admin=True,
        )

        AccountDeletionReconciliationAccess.objects.create(
            administrator=admin,
            granted_by=admin,
            is_enabled=True,
        )

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.claimed.attempt_id,
            administrator=admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            verified_storage_reference="different/asset.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            evidence_reference="test-mismatched-asset",
            explanation="Simulated absence evidence for another asset.",
        )

        confirmation = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.claimed.attempt_id,
            administrator=admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .DELETION_CONFIRMED
            ),
            evidence_reference=str(verification.pk),
            explanation="Test confirmation referencing mismatched evidence.",
        )

        with self.assertRaisesRegex(
            CleanupFinalizationError,
            "Verification evidence does not match the cleanup asset",
        ):
            finalize_verified_cleanup_job(
                self.job.pk,
                administrator=admin,
                attempt_id=self.claimed.attempt_id,
                confirmation_audit_id=confirmation.pk,
            )

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))
