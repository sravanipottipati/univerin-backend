import uuid
from datetime import timedelta
from unittest.mock import patch

from cloudinary.exceptions import NotFound

from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)
from users.deletion.reconciliation_verification import (
    verify_cleanup_asset,
)
from users.deletion.storage_verification import (
    StorageVerificationError,
)


@override_settings(
    ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED=True,
    TESTING_ACCOUNT_DELETION_CLEANUP=False,
)
class CloudinaryReconciliationIntegrationTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            phone_number="9876549611",
            password="TestPassword123!",
            full_name="Integration Administrator",
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
            phone_number="9876549612",
            password="TestPassword123!",
            full_name="Integration Test User",
            user_type="buyer",
        )

        self.reference = "private/integration-test.jpg"

        self.user.profile_photo = self.reference
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
            storage_reference=self.reference,
            resource_type="image",
            status="processing",
            attempts=1,
            attempt_id=self.attempt_id,
            lease_expires_at=(
                timezone.now() - timedelta(minutes=5)
            ),
        )

    def verify(self):
        return verify_cleanup_asset(
            self.job.pk,
            administrator=self.admin,
            attempt_id=self.attempt_id,
        )

    def test_real_verifier_integration_asset_exists(self):
        response = {
            "public_id": self.reference,
            "resource_type": "image",
            "type": "upload",
        }

        with patch(
            "users.deletion.reconciliation_verification.cloudinary_api.resource",
            return_value=response,
        ) as mock_resource:

            result = self.verify()

        self.assertEqual(result["verification_state"], "exists")
        self.assertFalse(result["finalization_allowed"])

        mock_resource.assert_called_once_with(
            self.reference,
            resource_type="image",
            type="upload",
        )

        self.assertTrue(
            AccountDeletionReconciliationAudit.objects.filter(
                cleanup_job=self.job,
            ).exists()
        )

    def test_real_verifier_integration_asset_absent(self):

        with patch(
            "users.deletion.reconciliation_verification.cloudinary_api.resource",
            side_effect=NotFound("Resource not found"),
        ):

            result = self.verify()

        self.assertEqual(result["verification_state"], "absent")
        self.assertFalse(result["finalization_allowed"])
        self.assertFalse(result["automatic_retry_allowed"])

        self.assertTrue(
            AccountDeletionReconciliationAudit.objects.filter(
                cleanup_job=self.job,
                decision=(
                    AccountDeletionReconciliationAudit.Decision
                    .ASSET_ABSENT_OBSERVED
                ),
            ).exists()
        )

    def test_cloudinary_network_failure_is_unknown(self):

        with patch(
            "users.deletion.reconciliation_verification.cloudinary_api.resource",
            side_effect=RuntimeError("Cloudinary unavailable"),
        ):

            result = self.verify()

        self.assertEqual(result["verification_state"], "unknown")
        self.assertFalse(result["finalization_allowed"])
        self.assertFalse(result["automatic_retry_allowed"])

    @override_settings(
        ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED=False
    )
    def test_verification_disabled_does_not_call_cloudinary(self):

        with patch(
            "users.deletion.reconciliation_verification.cloudinary_api.resource"
        ) as mock_resource:

            with self.assertRaises(StorageVerificationError):
                self.verify()

        mock_resource.assert_not_called()

    def test_verification_does_not_clear_original_reference(self):

        response = {
            "public_id": self.reference,
            "resource_type": "image",
            "type": "upload",
        }

        with patch(
            "users.deletion.reconciliation_verification.cloudinary_api.resource",
            return_value=response,
        ):

            self.verify()

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.profile_photo.name,
            self.reference,
        )

        self.job.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
