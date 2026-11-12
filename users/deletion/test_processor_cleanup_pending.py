from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request
from users.deletion.cleanup_models import AccountDeletionAsset


class ProcessorCleanupPendingTests(TestCase):

    def test_reprocessing_does_not_erase_buyer_with_pending_asset(self):
        buyer = User.objects.create_user(
            phone_number="9876549601",
            password="TestPassword123!",
            full_name="Buyer With Photo",
            user_type="buyer",
        )

        buyer.profile_photo = "profile_photos/test.jpg"
        buyer.save(update_fields=["profile_photo"])

        admin = User.objects.create_superuser(
            phone_number="9876549602",
            password="TestPassword123!",
            full_name="Deletion Admin",
            user_type="admin",
        )

        deletion_request = create_deletion_request(buyer)["request"]

        # First attempt creates the cleanup job.
        process_deletion_request(
            deletion_request.pk,
            approved_by=admin,
        )

        # Second attempt must not bypass pending cleanup.
        process_deletion_request(
            deletion_request.pk,
            approved_by=admin,
        )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

        jobs = AccountDeletionAsset.objects.filter(
            deletion_request=deletion_request,
        )

        self.assertEqual(jobs.count(), 1)
        self.assertEqual(jobs.get().status, "pending")
        self.assertEqual(jobs.get().attempts, 0)
