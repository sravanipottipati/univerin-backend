import uuid
from datetime import timedelta
from unittest.mock import patch

from cloudinary.exceptions import NotFound
from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AutomaticDeletionVerificationAudit,
)
from users.deletion.automatic_verification import (
    verify_automatic_cleanup_asset,
)


@override_settings(
    ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
    ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED=True,
    TESTING_ACCOUNT_DELETION_CLEANUP=True,
)
class AutomaticVerificationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549731",
            password="TestPassword123!",
            full_name="Automatic Verification Buyer",
            user_type="buyer",
        )
        self.reference = "private/automatic-verification-test.jpg"
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
            storage_deletion_confirmed_at=timezone.now() - timedelta(minutes=6),
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

    def verify(self):
        return verify_automatic_cleanup_asset(
            self.job.pk, self.attempt_id
        )

    def test_absent_asset_records_evidence_without_erasure(self):
        with patch(
            "users.deletion.automatic_verification.cloudinary_api.resource",
            side_effect=NotFound("Resource not found"),
        ):
            result = self.verify()

        self.assertEqual(result["verification_state"], "absent")
        self.assertFalse(result["cleanup_finalized"])
        self.assertFalse(result["account_erased"])
        self.assertTrue(
            AutomaticDeletionVerificationAudit.objects.filter(
                cleanup_job=self.job, state="absent"
            ).exists()
        )

        self.user.refresh_from_db()
        self.job.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.user.profile_photo.name, self.reference)

    def test_existing_asset_cannot_be_finalized(self):
        with patch(
            "users.deletion.automatic_verification.cloudinary_api.resource",
            return_value={
                "public_id": self.reference,
                "resource_type": "image",
                "type": "upload",
            },
        ):
            result = self.verify()

        self.assertEqual(result["verification_state"], "exists")
        self.assertFalse(result["cleanup_finalized"])

    def test_cloudinary_failure_is_unknown(self):
        with patch(
            "users.deletion.automatic_verification.cloudinary_api.resource",
            side_effect=RuntimeError("Network unavailable"),
        ):
            result = self.verify()

        self.assertEqual(result["verification_state"], "unknown")
        self.assertFalse(result["cleanup_finalized"])

    def test_stale_attempt_is_rejected(self):
        from users.deletion.automatic_verification import (
            AutomaticVerificationError,
        )

        with self.assertRaises(AutomaticVerificationError):
            verify_automatic_cleanup_asset(
                self.job.pk, uuid.uuid4()
            )

        self.assertFalse(
            AutomaticDeletionVerificationAudit.objects.filter(
                cleanup_job=self.job
            ).exists()
        )
