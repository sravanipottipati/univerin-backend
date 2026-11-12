from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.job_claim import claim_cleanup_job, CleanupClaimError


class PostgreSQLCleanupConcurrencyTests(TransactionTestCase):

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL")

        self.user = User.objects.create_user(
            phone_number="9876549831",
            password="TestPassword123!",
            full_name="PostgreSQL Concurrency Test",
            user_type="buyer",
        )

        self.user.profile_photo = "profile_photos/pg-concurrency.jpg"
        self.user.save(update_fields=["profile_photo"])

        request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(request)[0]

    def test_only_one_worker_can_claim_job(self):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                claim_cleanup_job(self.job.pk)
                return "claimed"
            except CleanupClaimError:
                return "rejected"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]

        self.job.refresh_from_db()

        self.assertEqual(results.count("claimed"), 1)
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(self.job.attempts, 1)
        self.assertIsNotNone(self.job.attempt_id)
        self.assertIsNotNone(self.job.lease_expires_at)
