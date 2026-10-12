from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from orders import test_delivery_otp
from orders.dp_views import DPOrderStatusUpdateView


class DeliveryNotificationTests(TestCase):
    def setUp(self):
        test_delivery_otp.DeliveryOTPTests.setUp(self)

    def verify(self, otp, user=None):
        return test_delivery_otp.DeliveryOTPTests.verify(self, otp, user)

    def test_pickup_notifies_buyer(self):
        self.order.dp_status = "arrived_at_shop"
        self.order.status = "preparing"
        self.order.delivery_otp = None
        self.order.save()

        request = self.factory.post(
            f"/dp/orders/{self.order.id}/status/",
            {"dp_status": "picked_up"},
            format="json",
        )
        force_authenticate(request, user=self.dp)

        with patch("orders.dp_views.create_notification") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                response = DPOrderStatusUpdateView.as_view()(
                    request, order_id=self.order.id
                )

        self.assertEqual(response.status_code, 200)
        notify.assert_called_once()
        self.assertEqual(
            notify.call_args.kwargs["notif_type"], "order_dispatched"
        )
        self.assertEqual(
            notify.call_args.kwargs["user"], self.buyer
        )

    def test_successful_delivery_notifies_buyer(self):
        with patch("orders.dp_views.create_notification") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.verify("123456")

        self.assertEqual(response.status_code, 200)
        notify.assert_called_once()
        self.assertEqual(
            notify.call_args.kwargs["notif_type"], "order_delivered"
        )
        self.assertEqual(
            notify.call_args.kwargs["user"], self.buyer
        )

    def test_incorrect_otp_does_not_notify_buyer(self):
        with patch("orders.dp_views.create_notification") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.verify("999999")

        self.assertEqual(response.status_code, 400)
        notify.assert_not_called()

    def test_delivery_notification_saved_to_database(self):
        from orders.models import Notification
        from orders.views import create_notification

        with self.captureOnCommitCallbacks(execute=True):
            response = self.verify("123456")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(
                user=self.buyer,
                order=self.order,
                type="order_delivered",
            ).count(),
            1,
        )

    def test_duplicate_delivery_notification_prevented(self):
        from orders.models import Notification
        from orders.views import create_notification

        for _ in range(2):
            create_notification(
                user=self.buyer,
                notif_type="order_delivered",
                title="Order Delivered",
                message="Your order has been delivered.",
                order=self.order,
            )

        self.assertEqual(
            Notification.objects.filter(
                user=self.buyer,
                order=self.order,
                type="order_delivered",
            ).count(),
            1,
        )
