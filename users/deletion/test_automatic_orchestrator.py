from unittest.mock import patch

from cloudinary.exceptions import NotFound
from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.automatic_orchestrator import (
    process_automatic_deletion_with_assets,
)


@override_settings(
    ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
    ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED=True,
    TESTING_ACCOUNT_DELETION_CLEANUP=True,
)
class AutomaticOrchestratorTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549751",
            password="TestPassword123!",
            full_name="Orchestrator Test Buyer",
            user_type="buyer",
        )

        self.reference = "private/orchestrator-test.jpg"
        self.user.profile_photo = self.reference
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

    def test_successful_cleanup_and_account_erasure(self):
        from users.deletion.storage_adapter import FakeStorageAdapter

        with (
            patch(
                "users.deletion.automatic_orchestrator.CloudinaryStorageAdapter",
                FakeStorageAdapter,
            ),
            patch(
                "users.deletion.automatic_verification.cloudinary_api.resource",
                side_effect=NotFound("Resource not found"),
            ),
        ):
            result = process_automatic_deletion_with_assets(
                self.request.pk
            )

        self.assertEqual(result.status, "completed")

        self.user.refresh_from_db()
        self.request.refresh_from_db()

        self.assertTrue(self.user.is_deleted)
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.request.status, "completed")

        self.assertEqual(
            AccountDeletionAsset.objects.filter(
                deletion_request=self.request,
                status="completed",
            ).count(),
            1,
        )

    def test_cloudinary_failure_preserves_account(self):
        from users.deletion.storage_adapter import FakeStorageAdapter
        from users.deletion.automatic_orchestrator import (
            AutomaticOrchestrationError,
        )

        with (
            patch(
                "users.deletion.automatic_orchestrator.CloudinaryStorageAdapter",
                FakeStorageAdapter,
            ),
            patch(
                "users.deletion.automatic_verification.cloudinary_api.resource",
                side_effect=RuntimeError("Cloudinary unavailable"),
            ),
        ):
            with self.assertRaises(AutomaticOrchestrationError):
                process_automatic_deletion_with_assets(self.request.pk)

        self.user.refresh_from_db()
        self.request.refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(self.request.status, "pending")
        self.assertEqual(self.user.profile_photo.name, self.reference)

        self.assertTrue(
            AccountDeletionAsset.objects.filter(
                deletion_request=self.request,
                status="processing",
            ).exists()
        )
