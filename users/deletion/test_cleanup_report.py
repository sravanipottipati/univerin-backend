from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job


class CleanupReportTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549821",
            password="TestPassword123!",
            full_name="Cleanup Report Test",
            user_type="buyer",
        )

        self.user.profile_photo = "profile_photos/report.jpg"
        self.user.save(update_fields=["profile_photo"])

        request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(request)[0]

    def run_report(self):
        output = StringIO()
        call_command("report_deletion_cleanup", stdout=output)
        return output.getvalue()

    def test_pending_job_not_reported(self):
        output = self.run_report()
        self.assertIn("Cleanup jobs requiring review: 0", output)

    def test_active_processing_job_not_reported(self):
        claim_cleanup_job(self.job.pk)

        output = self.run_report()
        self.assertIn("Cleanup jobs requiring review: 0", output)

    def test_expired_processing_job_reported(self):
        claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.job.lease_expires_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.job.save(update_fields=["lease_expires_at"])

        output = self.run_report()

        self.assertIn(str(self.job.pk), output)
        self.assertIn("Lease expired: True", output)
        self.assertIn("ADMINISTRATOR RECONCILIATION REQUIRED", output)
        self.assertIn("Cleanup jobs requiring review: 1", output)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "processing")

    def test_uncertain_storage_outcome_reported(self):
        claim_cleanup_job(self.job.pk)

        self.job.refresh_from_db()
        self.job.last_error = "Storage outcome uncertain"
        self.job.save(update_fields=["last_error"])

        output = self.run_report()

        self.assertIn(str(self.job.pk), output)
        self.assertIn("Storage outcome uncertain: True", output)
        self.assertIn("Cleanup jobs requiring review: 1", output)
