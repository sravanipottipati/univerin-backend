"""Tests for evidence-backed administrator cleanup confirmation."""

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)


class ReconciliationConfirmationTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="9876549751",
            password="TestPassword123!",
            user_type="admin",
            is_staff=True,
            is_admin=True,
        )

        AccountDeletionReconciliationAccess.objects.create(
            administrator=self.admin,
            granted_by=self.admin,
            is_enabled=True,
        )

        self.user = User.objects.create_user(
            phone_number="9876549752",
            password="TestPassword123!",
            user_type="buyer",
        )

        self.user.profile_photo = "private/confirmation-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.attempt_id = uuid.uuid4()

        self.job = AccountDeletionAsset.objects.create(
            deletion_request=self.request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/confirmation-test.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            attempt_id=self.attempt_id,
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

    def test_confirmation_without_verification_is_rejected(self):
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
            ReconciliationDecisionError,
        )

        with self.assertRaises(ReconciliationDecisionError):
            confirm_cleanup_deletion(
                self.job.pk,
                administrator=self.admin,
                attempt_id=self.attempt_id,
                verification_audit_id=uuid.uuid4(),
                explanation="Administrator reviewed the cleanup evidence.",
            )

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.filter(
                decision=(
                    AccountDeletionReconciliationAudit.Decision
                    .DELETION_CONFIRMED
                ),
            ).exists()
        )

    def test_valid_absence_evidence_allows_confirmation(self):
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
        )

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.attempt_id,
            administrator=self.admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            verified_storage_reference="private/confirmation-test.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            evidence_reference="cloudinary:asset-absent",
            explanation="Read-only storage verification reported absent.",
        )

        confirmation = confirm_cleanup_deletion(
            self.job.pk,
            administrator=self.admin,
            attempt_id=self.attempt_id,
            verification_audit_id=verification.pk,
            explanation="Administrator reviewed the absence evidence.",
        )

        self.assertEqual(
            confirmation.decision,
            AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED,
        )
        self.assertEqual(
            confirmation.evidence_reference,
            str(verification.pk),
        )
        self.assertEqual(confirmation.cleanup_job_id, self.job.pk)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(self.user.profile_photo)

    def test_stale_attempt_evidence_is_rejected(self):
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
            ReconciliationDecisionError,
        )

        old_attempt = uuid.uuid4()

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=old_attempt,
            administrator=self.admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            verified_storage_reference="private/confirmation-test.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            evidence_reference="cloudinary:old-attempt",
            explanation="Asset absent during a previous cleanup attempt.",
        )

        with self.assertRaises(ReconciliationDecisionError):
            confirm_cleanup_deletion(
                self.job.pk,
                administrator=self.admin,
                attempt_id=self.attempt_id,
                verification_audit_id=verification.pk,
                explanation="Reviewing evidence from an earlier attempt.",
            )

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.filter(
                cleanup_job=self.job,
                decision=(
                    AccountDeletionReconciliationAudit.Decision
                    .DELETION_CONFIRMED
                ),
            ).exists()
        )

    def test_revoked_administrator_cannot_confirm(self):
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
            ReconciliationDecisionError,
        )

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.attempt_id,
            administrator=self.admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            verified_storage_reference="private/confirmation-test.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            evidence_reference="cloudinary:asset-absent",
            explanation="Read-only storage verification reported absent.",
        )

        AccountDeletionReconciliationAccess.objects.filter(
            administrator=self.admin,
        ).update(is_enabled=False)

        with self.assertRaises(ReconciliationDecisionError):
            confirm_cleanup_deletion(
                self.job.pk,
                administrator=self.admin,
                attempt_id=self.attempt_id,
                verification_audit_id=verification.pk,
                explanation="Administrator reviewed the absence evidence.",
            )

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.filter(
                cleanup_job=self.job,
                decision=(
                    AccountDeletionReconciliationAudit.Decision
                    .DELETION_CONFIRMED
                ),
            ).exists()
        )

    def test_mismatched_asset_evidence_is_rejected(self):
        from users.deletion.reconciliation_models import (
            AccountDeletionReconciliationAudit,
        )
        from users.deletion.reconciliation_service import (
            confirm_cleanup_deletion,
            ReconciliationDecisionError,
        )

        verification = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=self.job,
            attempt_id=self.job.attempt_id,
            administrator=self.admin,
            decision=(
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED
            ),
            evidence_reference="cloudinary-admin-not-found",
            verified_storage_reference="private/different-asset.jpg",
            verified_resource_type="image",
            verified_storage_provider="django",
            explanation="Simulated observation for a different asset.",
        )

        with self.assertRaisesRegex(
            ReconciliationDecisionError,
            "Verification evidence does not match",
        ):
            confirm_cleanup_deletion(
                self.job.pk,
                administrator=self.admin,
                attempt_id=self.job.attempt_id,
                verification_audit_id=verification.pk,
                explanation="Administrator reviewed the absence evidence.",
            )

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.filter(
                cleanup_job=self.job,
                attempt_id=self.job.attempt_id,
                decision=(
                    AccountDeletionReconciliationAudit.Decision
                    .DELETION_CONFIRMED
                ),
            ).exists()
        )
