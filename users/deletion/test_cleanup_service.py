from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.cleanup_service import simulate_cleanup_attempt


class CleanupServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549301",
            password="TestPassword123!",
            full_name="Cleanup Simulation Buyer",
            user_type="buyer",
        )
        self.user.profile_photo = "profile_photos/simulation.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(self.request)[0]

    def test_simulation_does_not_delete_asset(self):
        result = simulate_cleanup_attempt(self.job.pk)

        self.job.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.attempts, 1)
        self.assertFalse(result["external_deletion_performed"])
        self.assertFalse(self.user.is_deleted)
        self.assertEqual(
            self.user.profile_photo.name,
            "profile_photos/simulation.jpg",
        )

    def test_simulation_can_be_retried(self):
        simulate_cleanup_attempt(self.job.pk)
        simulate_cleanup_attempt(self.job.pk)

        self.job.refresh_from_db()

        self.assertEqual(self.job.attempts, 2)
        self.assertEqual(self.job.status, "failed")
        self.assertIsNone(self.job.completed_at)
