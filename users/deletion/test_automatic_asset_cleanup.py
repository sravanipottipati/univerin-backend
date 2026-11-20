from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.automatic_asset_cleanup import (
    AutomaticAssetCleanupError,
    prepare_automatic_asset_cleanup,
)


@override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
class AutomaticAssetCleanupPreparationTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876549721",
            password="TestPassword123!",
            full_name="Automatic Cleanup Buyer",
            user_type="buyer",
        )
        self.request = AccountDeletionRequest.objects.create(
            user=self.buyer,
            account_type="buyer",
            status="pending",
        )

    def test_eligible_buyer_photo_creates_cleanup_job(self):
        self.buyer.profile_photo = "profile_photos/auto-test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        result = prepare_automatic_asset_cleanup(self.request.pk)

        self.assertTrue(result["eligible"])
        self.assertEqual(len(result["asset_jobs"]), 1)
        self.assertFalse(result["external_deletion_performed"])
        self.assertFalse(result["account_erased"])

        self.assertEqual(
            AccountDeletionAsset.objects.filter(
                deletion_request=self.request,
                status="pending",
            ).count(),
            1,
        )

        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertTrue(bool(self.buyer.profile_photo))

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=False)
    def test_disabled_flag_prevents_queue_creation(self):
        with self.assertRaises(AutomaticAssetCleanupError):
            prepare_automatic_asset_cleanup(self.request.pk)

        self.assertFalse(
            AccountDeletionAsset.objects.filter(
                deletion_request=self.request
            ).exists()
        )

    def test_mismatched_account_type_is_rejected(self):
        self.request.account_type = "vendor"
        self.request.save(update_fields=["account_type"])

        with self.assertRaises(AutomaticAssetCleanupError):
            prepare_automatic_asset_cleanup(self.request.pk)

        self.assertFalse(
            AccountDeletionAsset.objects.filter(
                deletion_request=self.request
            ).exists()
        )
