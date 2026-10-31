"""Tests for Expo push receipt verification."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from orders.models import PushNotificationJob
from orders.push_receipt_service import verify_push_receipts

User = get_user_model()


class PushReceiptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543240",
            password="TestPassword123!",
            user_type="delivery_partner",
        )
        self.user.fcm_token = "ExponentPushToken[receipt-test]"
        self.user.save(update_fields=["fcm_token"])

        self.job = PushNotificationJob.objects.create(
            user=self.user,
            push_token=self.user.fcm_token,
            title="Receipt Test",
            message="Testing Expo receipts",
            status="sent",
            expo_ticket_id="ticket-123",
        )

        PushNotificationJob.objects.filter(
            pk=self.job.pk
        ).update(
            updated_at=timezone.now() - timedelta(minutes=20)
        )

    def mock_response(self, receipts):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": receipts}
        return response

    @patch("orders.push_receipt_service.requests.post")
    def test_successful_receipt(self, mock_post):
        mock_post.return_value = self.mock_response({
            "ticket-123": {"status": "ok"}
        })

        self.assertEqual(verify_push_receipts(), 1)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "delivered")

    @patch("orders.push_receipt_service.requests.post")
    def test_failed_receipt(self, mock_post):
        mock_post.return_value = self.mock_response({
            "ticket-123": {
                "status": "error",
                "message": "Push delivery failed",
                "details": {"error": "MessageTooBig"},
            }
        })

        self.assertEqual(verify_push_receipts(), 1)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.last_error, "Push delivery failed")

    @patch("orders.push_receipt_service.requests.post")
    def test_missing_receipt_remains_sent(self, mock_post):
        mock_post.return_value = self.mock_response({})

        self.assertEqual(verify_push_receipts(), 0)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "sent")

    @patch("orders.push_receipt_service.requests.post")
    def test_invalid_device_token_is_removed(self, mock_post):
        mock_post.return_value = self.mock_response({
            "ticket-123": {
                "status": "error",
                "message": "Device is not registered",
                "details": {"error": "DeviceNotRegistered"},
            }
        })

        self.assertEqual(verify_push_receipts(), 1)
        self.user.refresh_from_db()
        self.job.refresh_from_db()

        self.assertEqual(self.user.fcm_token, "")
        self.assertEqual(self.job.status, "failed")

    @patch("orders.push_receipt_service.requests.post")
    def test_api_failure_keeps_job_sent(self, mock_post):
        mock_post.side_effect = ConnectionError("Network unavailable")

        self.assertEqual(verify_push_receipts(), 0)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "sent")

    @patch("orders.push_receipt_service.requests.post")
    def test_recent_job_is_not_checked(self, mock_post):
        PushNotificationJob.objects.filter(
            pk=self.job.pk
        ).update(updated_at=timezone.now())

        self.assertEqual(verify_push_receipts(), 0)
        mock_post.assert_not_called()

    @patch("orders.push_receipt_service.requests.post")
    def test_replaced_token_is_preserved(self, mock_post):
        self.user.fcm_token = "ExponentPushToken[new-device]"
        self.user.save(update_fields=["fcm_token"])

        mock_post.return_value = self.mock_response({
            "ticket-123": {
                "status": "error",
                "message": "Old device is not registered",
                "details": {"error": "DeviceNotRegistered"},
            }
        })

        self.assertEqual(verify_push_receipts(), 1)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.fcm_token,
            "ExponentPushToken[new-device]",
        )

    @patch("orders.push_receipt_service.requests.post")
    def test_receipt_older_than_24_hours_times_out(self, mock_post):
        PushNotificationJob.objects.filter(
            pk=self.job.pk
        ).update(
            updated_at=timezone.now() - timedelta(hours=25)
        )

        self.assertEqual(verify_push_receipts(), 0)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertIn("24 hours", self.job.last_error)
        mock_post.assert_not_called()

    @patch("orders.push_receipt_service.requests.post")
    def test_receipt_before_timeout_is_checked(self, mock_post):
        mock_post.return_value = self.mock_response({
            "ticket-123": {"status": "ok"}
        })

        PushNotificationJob.objects.filter(
            pk=self.job.pk
        ).update(
            updated_at=timezone.now() - timedelta(hours=23)
        )

        self.assertEqual(verify_push_receipts(), 1)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "delivered")

    @patch("orders.push_receipt_service.requests.post")
    def test_old_job_without_ticket_id_times_out(self, mock_post):
        PushNotificationJob.objects.filter(
            pk=self.job.pk
        ).update(
            expo_ticket_id="",
            updated_at=timezone.now() - timedelta(hours=25),
        )

        self.assertEqual(verify_push_receipts(), 0)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "failed")
        self.assertIn("24 hours", self.job.last_error)
        mock_post.assert_not_called()
