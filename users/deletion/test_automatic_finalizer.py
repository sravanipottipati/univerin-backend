import uuid
from datetime import timedelta
from unittest.mock import patch

from cloudinary.exceptions import NotFound
from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.automatic_verification import (
    verify_automatic_cleanup_asset,
)
from users.deletion.automatic_finalizer import (
    finalize_automatic_cleanup_job,
    AutomaticFinalizationError,
)


@override_settings(
    ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
    ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED=True,
    TESTING_ACCOUNT_DELETION_CLEANUP=True,
)
class AutomaticFinalizerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549741",
            password="TestPassword123!",
            full_name="Finalizer Test Buyer",
            user_type="buyer",
        )
        self.reference = "private/automatic-finalizer-test.jpg"
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

    def verify_absent(self):
        with patch(
            "users.deletion.automatic_verification.cloudinary_api.resource",
            side_effect=NotFound("Resource not found"),
        ):
            return verify_automatic_cleanup_asset(
                self.job.pk, self.attempt_id
            )

    def finalize(self, audit_id, attempt_id=None):
        return finalize_automatic_cleanup_job(
            self.job.pk,
            attempt_id=attempt_id or self.attempt_id,
            verification_audit_id=audit_id,
        )

    def test_verified_absence_finalizes_asset_only(self):
        verification = self.verify_absent()
        result = self.finalize(verification["audit_id"])

        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["account_erased"])

        self.job.refresh_from_db()
        self.user.refresh_from_db()
        self.request.refresh_from_db()

        self.assertEqual(self.job.status, "completed")
        self.assertFalse(bool(self.user.profile_photo))
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.request.status, "pending")

    def test_missing_verification_cannot_finalize(self):
        with self.assertRaises(AutomaticFinalizationError):
            self.finalize(uuid.uuid4())

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")

    def test_stale_attempt_cannot_finalize(self):
        verification = self.verify_absent()

        with self.assertRaises(AutomaticFinalizationError):
            self.finalize(
                verification["audit_id"],
                attempt_id=uuid.uuid4(),
            )

    def test_changed_asset_reference_cannot_finalize(self):
        verification = self.verify_absent()
        self.user.profile_photo = "private/replacement.jpg"
        self.user.save(update_fields=["profile_photo"])

        with self.assertRaises(Exception):
            self.finalize(verification["audit_id"])

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.profile_photo.name,
            "private/replacement.jpg",
        )

    def test_uncertain_execution_cannot_finalize(self):
        verification = self.verify_absent()

        self.job.last_error = "Storage outcome uncertain"
        self.job.save(update_fields=["last_error"])

        with self.assertRaises(AutomaticFinalizationError):
            self.finalize(verification["audit_id"])

    def test_missing_storage_confirmation_blocks_verification_and_finalization(self):
        from users.deletion.automatic_verification import (
            AutomaticVerificationError,
        )

        self.job.storage_deletion_confirmed_at = None
        self.job.save(update_fields=["storage_deletion_confirmed_at"])

        with patch(
            "users.deletion.automatic_verification.cloudinary_api.resource"
        ) as mock_resource:
            with self.assertRaises(AutomaticVerificationError):
                verify_automatic_cleanup_asset(
                    self.job.pk, self.attempt_id
                )

        mock_resource.assert_not_called()

        with self.assertRaises(AutomaticFinalizationError):
            self.finalize(uuid.uuid4())

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "processing")
        self.assertTrue(bool(self.user.profile_photo))
        self.assertTrue(self.user.is_active)
