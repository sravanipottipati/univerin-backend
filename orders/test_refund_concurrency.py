import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.db import connection, close_old_connections
from django.test import TransactionTestCase, override_settings

from users.models import User
from vendors.models import Vendor
from orders.models import Order, Refund
from orders.refund_service import (
    RefundError,
    reserve_order_refund,
    process_reserved_refund,
)


class RefundConcurrencyTests(TransactionTestCase):

    def setUp(self):
        self.buyer = User.objects.create(
            full_name="Concurrency Buyer",
            phone_number="9000000901",
            user_type="buyer",
        )
        seller = User.objects.create(
            full_name="Concurrency Seller",
            phone_number="9000000902",
            user_type="vendor",
        )
        vendor = Vendor.objects.create(
            user=seller,
            shop_name="Concurrency Test Shop",
            category="grocery",
            phone_number="9000000902",
            address="Test Address",
            town="Test Town",
            status="approved",
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            vendor=vendor,
            total_amount=Decimal("199.99"),
            delivery_address="Test Address",
            payment_mode="online",
            payment_status="paid",
            razorpay_order_id="order_concurrency_001",
            razorpay_payment_id="pay_concurrency_001",
            status="rejected",
        )

    @override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True)
    def test_second_worker_cannot_issue_duplicate_refund(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locking")

        refund, _ = reserve_order_refund(
            self.order.pk,
            reason="Seller rejected order",
        )

        first_started = threading.Event()
        release_first = threading.Event()
        results = []

        client = MagicMock()

        def blocked_payment_fetch(payment_id):
            first_started.set()
            if not release_first.wait(timeout=10):
                raise TimeoutError("Test synchronization timed out")
            return {
                "id": payment_id,
                "order_id": "order_concurrency_001",
                "currency": "INR",
                "status": "captured",
                "captured": True,
                "amount": 19999,
                "amount_refunded": 0,
            }

        client.payment.fetch.side_effect = blocked_payment_fetch
        client.payment.refund.return_value = {
            "id": "rfnd_concurrency_001",
            "payment_id": "pay_concurrency_001",
            "currency": "INR",
            "amount": 19999,
            "status": "processed",
        }

        def first_worker():
            close_old_connections()
            try:
                result = process_reserved_refund(refund.pk)
                results.append(result.processing_state)
            except Exception as exc:
                results.append(type(exc).__name__)
            finally:
                close_old_connections()

        with patch(
            "orders.payment_views.get_razorpay_client",
            return_value=client,
        ):
            thread = threading.Thread(target=first_worker)
            thread.start()

            try:
                self.assertTrue(
                    first_started.wait(timeout=10),
                    "First worker did not reach payment verification",
                )

                with self.assertRaises(RefundError):
                    process_reserved_refund(refund.pk)
            finally:
                release_first.set()
                thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(results, ["completed"])

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "completed")
        client.payment.refund.assert_called_once()
