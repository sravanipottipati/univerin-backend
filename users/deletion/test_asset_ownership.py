from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_worker import (
    inspect_cleanup_job,
    AssetCleanupBlockedError,
)


class AssetOwnershipTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            phone_number="9876549101",
            password="TestPassword123!",
            full_name="Asset Owner",
            user_type="buyer",
        )
        self.owner.profile_photo = "profile_photos/shared.jpg"
        self.owner.save(update_fields=["profile_photo"])

        self.deletion_request = AccountDeletionRequest.objects.create(
            user=self.owner,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(
            self.deletion_request
        )[0]

    def test_unique_reference_passes_dry_run(self):
        result = inspect_cleanup_job(self.job.pk)

        self.assertTrue(result["reference_verified"])
        self.assertFalse(result["ready_for_external_cleanup"])

    def test_shared_reference_blocks_cleanup(self):
        other = User.objects.create_user(
            phone_number="9876549102",
            password="TestPassword123!",
            full_name="Other Buyer",
            user_type="buyer",
        )
        other.profile_photo = "profile_photos/shared.jpg"
        other.save(update_fields=["profile_photo"])

        with self.assertRaises(AssetCleanupBlockedError):
            inspect_cleanup_job(self.job.pk)

    def test_different_reference_does_not_block(self):
        other = User.objects.create_user(
            phone_number="9876549103",
            password="TestPassword123!",
            full_name="Other Buyer",
            user_type="buyer",
        )
        other.profile_photo = "profile_photos/other.jpg"
        other.save(update_fields=["profile_photo"])

        result = inspect_cleanup_job(self.job.pk)

        self.assertTrue(result["reference_verified"])
