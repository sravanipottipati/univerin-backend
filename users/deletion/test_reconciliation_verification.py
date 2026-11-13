import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)
from users.deletion.reconciliation_verification import (
    ReconciliationVerificationError,
    verify_cleanup_asset,
)
from users.deletion.storage_verification import (
    FakeStorageVerifier,
    StorageVerificationResult,
)


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class ReconciliationVerificationTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="9876549601",
            password="TestPassword123!",
            full_name="Verification Administrator",
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
            phone_number="9876549602",
            password="TestPassword123!",
            full_name="Deletion User",
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
            storage_reference="private/verification-test.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            attempt_id=self.attempt_id,
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

    def verify(self, state="unknown", **overrides):
        params = {
            "administrator": self.admin,
            "attempt_id": self.attempt_id,
            "verifier": FakeStorageVerifier(state=state),
        }
        params.update(overrides)
        return verify_cleanup_asset(self.job.pk, **params)

    def assert_job_unchanged(self):
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(
            self.job.storage_reference,
            "private/verification-test.jpg",
        )
        self.assertEqual(self.job.attempt_id, self.attempt_id)

    def test_asset_exists(self):
        result = self.verify("exists")
        self.assertEqual(result["verification_state"], "exists")
        self.assertFalse(result["finalization_allowed"])
        self.assert_job_unchanged()

    def test_asset_absent_does_not_finalize(self):
        result = self.verify("absent")
        self.assertEqual(result["verification_state"], "absent")
        self.assertFalse(result["finalization_allowed"])
        self.assert_job_unchanged()

        audit = AccountDeletionReconciliationAudit.objects.get(
            pk=result["audit_id"]
        )
        self.assertEqual(
            audit.decision,
            AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED,
        )

    def test_unknown_state(self):
        result = self.verify("unknown")
        self.assertEqual(result["verification_state"], "unknown")
        self.assertFalse(result["automatic_retry_allowed"])
        self.assert_job_unchanged()

    def test_disabled_grant_rejected(self):
        self.grant.is_enabled = False
        self.grant.save(update_fields=["is_enabled"])

        with self.assertRaises(ReconciliationVerificationError):
            self.verify("absent")

        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.exists()
        )

    def test_stale_attempt_rejected(self):
        with self.assertRaises(ReconciliationVerificationError):
            self.verify("absent", attempt_id=uuid.uuid4())

    def test_healthy_job_rejected(self):
        self.job.lease_expires_at = (
            timezone.now() + timedelta(minutes=10)
        )
        self.job.save(update_fields=["lease_expires_at"])

        with self.assertRaises(ReconciliationVerificationError):
            self.verify("absent")

    def test_invalid_provider_response_rejected(self):
        class InvalidVerifier:
            def verify(self, reference, *, resource_type, storage):
                return StorageVerificationResult(
                    state="invalid",
                    provider=storage,
                )

        with self.assertRaises(ReconciliationVerificationError):
            self.verify(verifier=InvalidVerifier())

    @override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=False)
    def test_fake_verifier_disabled_outside_tests(self):
        with self.assertRaises(ReconciliationVerificationError):
            self.verify("absent")
