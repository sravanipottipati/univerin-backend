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
from users.deletion.reconciliation_service import (
    ReconciliationDecisionError,
    begin_cleanup_investigation,
)


class ReconciliationServiceTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Reconciliation Administrator",
            user_type="admin",
            is_staff=True,
            is_admin=True,
        )

        self.grant = AccountDeletionReconciliationAccess.objects.create(
            administrator=self.admin,
            granted_by=self.admin,
            is_enabled=True,
        )

        self.user = User.objects.create_user(
            phone_number="9876549702",
            password="TestPassword123!",
            full_name="Deletion Test User",
            user_type="buyer",
        )

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
            storage_reference="private/test-reconciliation.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            attempt_id=self.attempt_id,
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

    def investigate(self, **overrides):
        params = {
            "administrator": self.admin,
            "attempt_id": self.attempt_id,
            "explanation": "Investigating expired cleanup attempt.",
        }
        params.update(overrides)
        return begin_cleanup_investigation(self.job.pk, **params)

    def test_authorized_investigation_creates_audit(self):
        audit = self.investigate()

        self.assertEqual(
            audit.decision,
            AccountDeletionReconciliationAudit.Decision.INVESTIGATING,
        )
        self.assertEqual(audit.cleanup_job_id, self.job.pk)
        self.assertEqual(audit.attempt_id, self.attempt_id)
        self.assertEqual(audit.administrator_id, self.admin.pk)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(
            self.job.storage_reference,
            "private/test-reconciliation.jpg",
        )

    def test_disabled_grant_rejected(self):
        self.grant.is_enabled = False
        self.grant.save(update_fields=["is_enabled"])

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate()

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.exists()
        )

    def test_staff_admin_without_grant_rejected(self):
        other_admin = User.objects.create_user(
            phone_number="9876549703",
            password="TestPassword123!",
            full_name="Unapproved Administrator",
            user_type="admin",
            is_staff=True,
            is_admin=True,
        )

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate(administrator=other_admin)

    def test_stale_attempt_rejected(self):
        with self.assertRaises(ReconciliationDecisionError):
            self.investigate(attempt_id=uuid.uuid4())

    def test_healthy_processing_job_rejected(self):
        self.job.lease_expires_at = (
            timezone.now() + timedelta(minutes=10)
        )
        self.job.save(update_fields=["lease_expires_at"])

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate()

    def test_completed_job_rejected(self):
        self.job.status = "completed"
        self.job.save(update_fields=["status"])

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate()

    def test_short_explanation_rejected(self):
        with self.assertRaises(ReconciliationDecisionError):
            self.investigate(explanation="short")

    def test_revoked_staff_access_rejected(self):
        self.admin.is_staff = False
        self.admin.save(update_fields=["is_staff"])

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate()

    def test_stale_administrator_object_rejected(self):
        stale_admin = User.objects.get(pk=self.admin.pk)

        User.objects.filter(pk=self.admin.pk).update(is_active=False)

        with self.assertRaises(ReconciliationDecisionError):
            self.investigate(administrator=stale_admin)

    def test_audit_record_cannot_be_modified(self):
        audit = self.investigate()

        audit.explanation = "Modified explanation"

        with self.assertRaises(ValueError):
            audit.save()

        audit.refresh_from_db()

        self.assertEqual(
            audit.explanation,
            "Investigating expired cleanup attempt.",
        )

    def test_audit_record_cannot_be_deleted(self):
        audit = self.investigate()

        with self.assertRaises(ValueError):
            audit.delete()

        self.assertTrue(
            AccountDeletionReconciliationAudit.objects.filter(
                pk=audit.pk
            ).exists()
        )
