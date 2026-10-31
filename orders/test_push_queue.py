"""Tests for UNIVERIN's database-backed push notification queue."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from orders.models import PushNotificationJob
from orders.push_service import queue_push_notification

User = get_user_model()


class PushQueueTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543210",
            password="TestPassword123!",
            user_type="delivery_partner",
        )
        self.user.fcm_token = "ExponentPushToken[test-token]"
        self.user.save(update_fields=["fcm_token"])

    def test_push_job_created(self):
        job = queue_push_notification(
            user=self.user,
            title="Test Notification",
            message="Testing UNIVERIN push notifications",
            payload={"type": "test"},
        )

        self.assertIsNotNone(job)
        self.assertEqual(PushNotificationJob.objects.count(), 1)
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.attempts, 0)
        self.assertEqual(job.payload["type"], "test")
        self.assertEqual(job.push_token, self.user.fcm_token)

    def test_no_push_job_without_token(self):
        self.user.fcm_token = ""
        self.user.save(update_fields=["fcm_token"])

        job = queue_push_notification(
            user=self.user,
            title="Test",
            message="No push token",
        )

        self.assertIsNone(job)
        self.assertEqual(PushNotificationJob.objects.count(), 0)

    def test_multiple_standard_notifications_are_queued(self):
        for number in range(2):
            queue_push_notification(
                user=self.user,
                title=f"Notification {number}",
                message="UNIVERIN test message",
            )

        self.assertEqual(PushNotificationJob.objects.count(), 2)

    def test_push_job_has_scheduling_timestamp(self):
        before = timezone.now() - timedelta(seconds=1)

        job = queue_push_notification(
            user=self.user,
            title="Scheduled Notification",
            message="Testing retry scheduling",
        )

        after = timezone.now() + timedelta(seconds=1)

        self.assertGreaterEqual(job.next_attempt_at, before)
        self.assertLessEqual(job.next_attempt_at, after)

    def test_queue_does_not_call_expo(self):
        from unittest.mock import patch

        with patch("requests.post") as mock_post:
            queue_push_notification(
                user=self.user,
                title="Async Test",
                message="This should only write to PostgreSQL",
            )

        mock_post.assert_not_called()


class PushWorkerTests(TestCase):
    """Test Expo push processing without sending real notifications."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543211",
            password="TestPassword123!",
            user_type="delivery_partner",
        )
        self.user.fcm_token = "ExponentPushToken[test-worker-token]"
        self.user.save(update_fields=["fcm_token"])

    def make_job(self):
        return queue_push_notification(
            user=self.user,
            title="UNIVERIN Test",
            message="Background push worker test",
            payload={"type": "test"},
        )

    def test_successful_expo_push(self):
        from unittest.mock import Mock, patch
        from orders.management.commands.run_push_notification_worker import (
            claim_job,
            process_job,
        )

        job = self.make_job()

        response = Mock()
        response.json.return_value = {
            "data": {
                "status": "ok",
                "id": "expo-test-ticket-123",
            }
        }
        response.raise_for_status.return_value = None

        with patch("orders.management.commands.run_push_notification_worker.requests.post",
                   return_value=response) as mock_post:
            claimed_id = claim_job()
            self.assertEqual(claimed_id, job.pk)
            process_job(claimed_id)

        job.refresh_from_db()
        self.assertEqual(job.status, "sent")
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.expo_ticket_id, "expo-test-ticket-123")
        mock_post.assert_called_once()

    def test_failed_push_is_scheduled_for_retry(self):
        from unittest.mock import patch
        from orders.management.commands.run_push_notification_worker import (
            claim_job,
            process_job,
        )

        job = self.make_job()

        with patch(
            "orders.management.commands.run_push_notification_worker.requests.post",
            side_effect=Exception("Temporary network failure"),
        ):
            claimed_id = claim_job()
            process_job(claimed_id)

        job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.attempts, 1)
        self.assertIn("Temporary network failure", job.last_error)
        self.assertGreater(job.next_attempt_at, timezone.now())

    def test_invalidated_token_is_not_sent(self):
        from unittest.mock import patch
        from orders.management.commands.run_push_notification_worker import (
            claim_job,
            process_job,
        )

        job = self.make_job()

        self.user.fcm_token = "ExponentPushToken[replacement-token]"
        self.user.save(update_fields=["fcm_token"])

        with patch(
            "orders.management.commands.run_push_notification_worker.requests.post"
        ) as mock_post:
            claimed_id = claim_job()
            process_job(claimed_id)

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("no longer registered", job.last_error)
        mock_post.assert_not_called()

    def test_stale_processing_job_is_recovered(self):
        from orders.management.commands.run_push_notification_worker import (
            recover_stale_jobs,
        )

        job = self.make_job()
        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=1,
            updated_at=timezone.now() - timedelta(minutes=2),
        )

        recovered_count = recover_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(recovered_count, 1)
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.attempts, 1)
        self.assertLessEqual(job.next_attempt_at, timezone.now())

    def test_exhausted_processing_job_is_failed(self):
        from orders.management.commands.run_push_notification_worker import (
            recover_stale_jobs,
            MAX_ATTEMPTS,
        )

        job = self.make_job()
        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=MAX_ATTEMPTS,
            updated_at=timezone.now() - timedelta(minutes=2),
        )

        recovered_count = recover_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(recovered_count, 0)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempts, MAX_ATTEMPTS)

    def test_recent_processing_job_is_not_recovered(self):
        from orders.management.commands.run_push_notification_worker import (
            recover_stale_jobs,
        )

        job = self.make_job()
        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=1,
            updated_at=timezone.now(),
        )

        recovered_count = recover_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(recovered_count, 0)
        self.assertEqual(job.status, "processing")


class DeliveryOfferPushTests(TestCase):
    """Ensure push notifications respect delivery-offer validity."""

    def setUp(self):
        from orders.models import Order, DeliveryOffer
        from vendors.models import Vendor

        self.dp = User.objects.create_user(
            phone_number="9876543220",
            password="TestPassword123!",
            user_type="delivery_partner",
        )
        self.dp.fcm_token = "ExponentPushToken[offer-test]"
        self.dp.save(update_fields=["fcm_token"])

        self.buyer = User.objects.create_user(
            phone_number="9876543221",
            password="TestPassword123!",
            user_type="buyer",
        )

        self.vendor_user = User.objects.create_user(
            phone_number="9876543222",
            password="TestPassword123!",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.vendor_user,
            shop_name="UNIVERIN Test Shop",
            category="restaurant",
            phone_number="9876543222",
            address="Test Address",
            town="Test Town",
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            vendor=self.vendor,
            total_amount="250.00",
            delivery_address="Test Delivery Address",
        )

        self.offer = DeliveryOffer.objects.create(
            order=self.order,
            delivery_partner=self.dp,
            status="pending",
            expires_at=timezone.now() + timedelta(seconds=30),
        )

    def make_offer_job(self):
        return queue_push_notification(
            user=self.dp,
            title="New Delivery Request",
            message="Open UNIVERIN to review this request.",
            delivery_offer=self.offer,
        )

    def test_expired_offer_is_not_sent(self):
        from unittest.mock import patch
        from orders.management.commands.run_push_notification_worker import (
            claim_job,
            process_job,
        )

        job = self.make_offer_job()

        self.offer.expires_at = timezone.now() - timedelta(seconds=1)
        self.offer.save(update_fields=["expires_at"])

        with patch(
            "orders.management.commands.run_push_notification_worker.requests.post"
        ) as mock_post:
            claimed_id = claim_job()
            process_job(claimed_id)

        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("expired", job.last_error)
        mock_post.assert_not_called()

    def test_inactive_offer_is_not_sent(self):
        from unittest.mock import patch
        from orders.management.commands.run_push_notification_worker import (
            claim_job,
            process_job,
        )

        for status in ("cancelled", "rejected"):
            with self.subTest(status=status):
                self.offer.status = status
                self.offer.save(update_fields=["status"])

                PushNotificationJob.objects.all().delete()
                job = self.make_offer_job()

                with patch(
                    "orders.management.commands.run_push_notification_worker.requests.post"
                ) as mock_post:
                    claimed_id = claim_job()
                    process_job(claimed_id)

                job.refresh_from_db()
                self.assertEqual(job.status, "failed")
                mock_post.assert_not_called()

    def test_duplicate_offer_job_is_prevented(self):
        first_job = self.make_offer_job()
        second_job = self.make_offer_job()

        self.assertEqual(first_job.pk, second_job.pk)
        self.assertEqual(PushNotificationJob.objects.count(), 1)
        self.assertEqual(
            first_job.payload["offer_id"],
            str(self.offer.pk),
        )
        self.assertEqual(
            first_job.payload["type"],
            "delivery_offer",
        )

    def test_stale_worker_cannot_overwrite_new_attempt(self):
        from orders.management.commands.run_push_notification_worker import (
            save_if_current,
        )

        job = self.make_offer_job()

        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=1,
        )
        job.refresh_from_db()

        # Simulate another worker reclaiming this job.
        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=2,
        )

        updated = save_if_current(
            job,
            status="sent",
            expo_ticket_id="old-worker-ticket",
        )

        job.refresh_from_db()

        self.assertFalse(updated)
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.expo_ticket_id, "")

    def test_completed_job_cannot_be_overwritten(self):
        from orders.management.commands.run_push_notification_worker import (
            save_if_current,
        )

        job = self.make_offer_job()

        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=1,
        )
        job.refresh_from_db()

        # Simulate successful completion by another operation.
        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="sent",
            expo_ticket_id="original-ticket",
        )

        updated = save_if_current(
            job,
            status="failed",
            last_error="Outdated worker result",
        )

        job.refresh_from_db()

        self.assertFalse(updated)
        self.assertEqual(job.status, "sent")
        self.assertEqual(job.expo_ticket_id, "original-ticket")
        self.assertEqual(job.last_error, "")


class PushOwnershipTests(TestCase):
    """Verify stale workers cannot initiate Expo requests."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543230",
            password="TestPassword123!",
            user_type="delivery_partner",
        )
        self.user.fcm_token = "ExponentPushToken[ownership-test]"
        self.user.save(update_fields=["fcm_token"])

    def test_lost_ownership_prevents_expo_request(self):
        from unittest.mock import patch
        from orders.management.commands.run_push_notification_worker import (
            process_job,
        )

        job = queue_push_notification(
            user=self.user,
            title="Ownership Test",
            message="Stale workers must not send this notification",
        )

        # Simulate an old worker reading attempt 1, followed by
        # another worker taking ownership as attempt 2.
        original_get = PushNotificationJob.objects.get

        def change_ownership_after_read(*args, **kwargs):
            result = original_get(*args, **kwargs)
            PushNotificationJob.objects.filter(pk=result.pk).update(
                status="processing",
                attempts=2,
            )
            return result

        # The worker reads through select_related().get(), so patch
        # that query path at the QuerySet level.
        from django.db.models.query import QuerySet

        original_queryset_get = QuerySet.get
        changed = False

        def intercepted_get(queryset, *args, **kwargs):
            nonlocal changed
            result = original_queryset_get(queryset, *args, **kwargs)

            if (
                isinstance(result, PushNotificationJob)
                and result.pk == job.pk
                and not changed
            ):
                changed = True
                PushNotificationJob.objects.filter(pk=job.pk).update(
                    status="processing",
                    attempts=2,
                )

            return result

        PushNotificationJob.objects.filter(pk=job.pk).update(
            status="processing",
            attempts=1,
        )

        with patch.object(QuerySet, "get", intercepted_get):
            with patch(
                "orders.management.commands."
                "run_push_notification_worker.requests.post"
            ) as mock_post:
                process_job(job.pk)

        job.refresh_from_db()

        self.assertTrue(changed)
        self.assertEqual(job.status, "processing")
        self.assertEqual(job.attempts, 2)
        mock_post.assert_not_called()
