from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.cleanup_finalizer import finalize_cleanup_job
from users.deletion.processor import process_deletion_request


class CompletedCleanupFlowTests(TestCase):

    def test_buyer_erasure_after_completed_cleanup(self):
        buyer = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Completed Cleanup Buyer",
            user_type="buyer",
        )
        buyer.profile_photo = "profile_photos/completed-flow.jpg"
        buyer.save(update_fields=["profile_photo"])

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        job = queue_account_deletion_assets(deletion_request)[0]

        # Simulated confirmation only; no Cloudinary call.
        claim_cleanup_job(job.pk)
        finalize_cleanup_job(
            job.pk,
            storage_result={"result": "ok"},
        )

        admin = User.objects.create_user(
            phone_number="9876549702",
            password="TestPassword123!",
            full_name="Deletion Test Admin",
            user_type="buyer",
        )
        admin.is_staff = True
        admin.is_admin = True
        admin.save(update_fields=["is_staff", "is_admin"])

        result = process_deletion_request(
            deletion_request.pk,
            approved_by=admin,
        )

        buyer.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(job.status, "completed")
        self.assertEqual(result.status, "completed")
        self.assertTrue(buyer.is_deleted)
        self.assertFalse(buyer.is_active)
