from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.dp_views import DPOrderStatusUpdateView, DPVerifyDeliveryOTPView
from orders import test_delivery_otp


class DeliveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        test_delivery_otp.DeliveryOTPTests.setUp(self)

        self.order.dp_status = "arrived_at_shop"
        self.order.status = "preparing"
        self.order.delivery_otp = None
        self.order.save()

    def test_simultaneous_pickup_requests(self):
        barrier = Barrier(2)

        def pickup():
            close_old_connections()
            try:
                request = APIRequestFactory().post(
                    f"/dp/orders/{self.order.id}/status/",
                    {"dp_status": "picked_up"},
                    format="json",
                )
                force_authenticate(request, user=self.dp)

                barrier.wait(timeout=10)

                response = DPOrderStatusUpdateView.as_view()(
                    request, order_id=self.order.id
                )
                return response.status_code
            finally:
                connection.close()

        with patch(
            "orders.dp_views.secrets.randbelow",
            return_value=554321,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(pickup) for _ in range(2)]
                results = [future.result(timeout=20) for future in futures]

        self.assertEqual(sorted(results), [200, 400])

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "picked_up")
        self.assertEqual(self.order.status, "dispatched")
        self.assertEqual(self.order.delivery_otp, "654321")

    def test_simultaneous_delivery_otp_verification(self):
        self.order.dp_status = "arrived_at_buyer"
        self.order.status = "dispatched"
        self.order.delivery_otp = "123456"
        self.order.delivery_otp_attempts = 0
        self.order.save()

        barrier = Barrier(2)

        def verify():
            close_old_connections()
            try:
                request = APIRequestFactory().post(
                    f"/dp/orders/{self.order.id}/verify-delivery-otp/",
                    {"otp": "123456"},
                    format="json",
                )
                force_authenticate(request, user=self.dp)

                barrier.wait(timeout=10)

                response = DPVerifyDeliveryOTPView.as_view()(
                    request, order_id=self.order.id
                )
                return response.status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(verify) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]

        self.assertEqual(sorted(results), [200, 400])

        self.order.refresh_from_db()
        self.assertEqual(self.order.dp_status, "delivered")
        self.assertEqual(self.order.status, "delivered")
        self.assertIsNone(self.order.delivery_otp)
        self.assertEqual(self.order.delivery_otp_attempts, 0)

