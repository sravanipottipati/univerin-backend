from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from orders.models import Order, Refund
from orders.refund_service import reserve_order_refund, RefundError


class RefundReservationTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create(
            full_name="Refund Test Buyer",
            phone_number="9000000801",
            user_type="buyer",
        )
        self.seller = User.objects.create(
            full_name="Refund Test Seller",
            phone_number="9000000802",
            user_type="vendor",
        )
        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="Refund Test Shop",
            category="grocery",
            phone_number="9000000802",
            address="Test Address",
            town="Test Town",
            status="approved",
        )
        self.order = Order.objects.create(
            buyer=self.buyer,
            vendor=self.vendor,
            total_amount=Decimal("199.99"),
            delivery_address="Test Address",
            payment_mode="online",
            payment_status="paid",
            razorpay_order_id="order_refund_test_001",
            razorpay_payment_id="pay_refund_test_001",
            status="placed",
        )

    def test_reserves_full_refund_in_paise(self):
        refund, created = reserve_order_refund(
            self.order.pk,
            reason="Seller rejected order",
        )

        self.assertTrue(created)
        self.assertEqual(refund.amount_paise, 19999)
        self.assertEqual(refund.processing_state, "reserved")
        self.assertEqual(
            refund.razorpay_payment_id,
            "pay_refund_test_001",
        )

    def test_repeated_reservation_is_idempotent(self):
        first, first_created = reserve_order_refund(
            self.order.pk,
            reason="Seller rejected order",
        )
        second, second_created = reserve_order_refund(
            self.order.pk,
            reason="Seller rejected order",
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Refund.objects.count(), 1)

    def test_cod_order_is_rejected(self):
        self.order.payment_mode = "cod"
        self.order.save(update_fields=["payment_mode"])

        with self.assertRaises(RefundError):
            reserve_order_refund(
                self.order.pk,
                reason="Order cancelled",
            )

        self.assertEqual(Refund.objects.count(), 0)

    def test_unpaid_order_is_rejected(self):
        self.order.payment_status = "pending"
        self.order.save(update_fields=["payment_status"])

        with self.assertRaises(RefundError):
            reserve_order_refund(
                self.order.pk,
                reason="Order cancelled",
            )

        self.assertEqual(Refund.objects.count(), 0)

    def test_existing_manual_refund_requires_review(self):
        Refund.objects.create(
            order=self.order,
            requested_by=self.buyer,
            reason="Existing refund request",
        )

        with self.assertRaisesMessage(
            RefundError,
            "An existing refund request requires review",
        ):
            reserve_order_refund(
                self.order.pk,
                reason="Seller rejected order",
            )

        self.assertEqual(Refund.objects.count(), 1)

    def prepare_refund(self):
        self.order.status = "rejected"
        self.order.save(update_fields=["status"])
        refund, _ = reserve_order_refund(
            self.order.pk,
            reason="Seller rejected order",
        )
        return refund

    def mock_payment(self):
        return {
            "id": "pay_refund_test_001",
            "order_id": "order_refund_test_001",
            "currency": "INR",
            "status": "captured",
            "captured": True,
            "amount": 19999,
            "amount_refunded": 0,
        }

    def test_refund_processing_disabled_by_default(self):
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=False):
            with self.assertRaises(RefundError):
                process_reserved_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "reserved")

    def test_successful_razorpay_refund(self):
        from unittest.mock import MagicMock, patch
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        client.payment.fetch.return_value = self.mock_payment()
        client.payment.refund.return_value = {
            "id": "rfnd_test_001",
            "payment_id": "pay_refund_test_001",
            "amount": 19999,
            "currency": "INR",
            "status": "processed",
        }

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                result = process_reserved_refund(refund.pk)

        self.assertEqual(result.processing_state, "completed")
        self.assertEqual(result.razorpay_refund_id, "rfnd_test_001")
        self.assertIsNotNone(result.completed_at)
        client.payment.refund.assert_called_once()

    def test_pending_razorpay_refund(self):
        from unittest.mock import MagicMock, patch
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        client.payment.fetch.return_value = self.mock_payment()
        client.payment.refund.return_value = {
            "id": "rfnd_test_pending",
            "payment_id": "pay_refund_test_001",
            "amount": 19999,
            "currency": "INR",
            "status": "pending",
        }

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                result = process_reserved_refund(refund.pk)

        self.assertEqual(result.processing_state, "initiated")
        self.assertEqual(result.razorpay_refund_id, "rfnd_test_pending")
        self.assertIsNone(result.completed_at)

    def test_payment_mismatch_prevents_refund(self):
        from unittest.mock import MagicMock, patch
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        payment = self.mock_payment()
        payment["amount"] = 10000
        client.payment.fetch.return_value = payment

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                with self.assertRaises(RefundError):
                    process_reserved_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "requires_review")
        client.payment.refund.assert_not_called()

    def test_timeout_does_not_trigger_duplicate_refund(self):
        from unittest.mock import MagicMock, patch
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        client.payment.fetch.return_value = self.mock_payment()
        client.payment.refund.side_effect = TimeoutError(
            "Razorpay request timed out"
        )

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                with self.assertRaises(RefundError):
                    process_reserved_refund(refund.pk)

                with self.assertRaises(RefundError):
                    process_reserved_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "requires_review")
        client.payment.refund.assert_called_once()

    def test_seller_rejection_reserves_refund(self):
        from orders.refund_service import transition_order_with_refund

        order = transition_order_with_refund(
            self.order.pk, target_status="rejected"
        )

        self.assertEqual(order.status, "rejected")
        refund = Refund.objects.get(order=order)
        self.assertEqual(refund.amount_paise, 19999)
        self.assertEqual(refund.processing_state, "reserved")

    def test_buyer_cancellation_reserves_refund(self):
        from orders.refund_service import transition_order_with_refund

        order = transition_order_with_refund(
            self.order.pk, target_status="cancelled"
        )

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(Refund.objects.filter(order=order).count(), 1)

    def test_cod_cancellation_does_not_create_refund(self):
        from orders.refund_service import transition_order_with_refund

        self.order.payment_mode = "cod"
        self.order.payment_status = "pending"
        self.order.save(update_fields=["payment_mode", "payment_status"])

        order = transition_order_with_refund(
            self.order.pk, target_status="cancelled"
        )

        self.assertEqual(order.status, "cancelled")
        self.assertFalse(Refund.objects.filter(order=order).exists())

    def test_duplicate_cancellation_is_blocked(self):
        from orders.refund_service import transition_order_with_refund

        transition_order_with_refund(
            self.order.pk, target_status="cancelled"
        )

        with self.assertRaises(RefundError):
            transition_order_with_refund(
                self.order.pk, target_status="cancelled"
            )

        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)

    def test_failed_reservation_rolls_back_cancellation(self):
        from orders.refund_service import transition_order_with_refund

        self.order.razorpay_payment_id = None
        self.order.save(update_fields=["razorpay_payment_id"])

        with self.assertRaises(RefundError):
            transition_order_with_refund(
                self.order.pk, target_status="cancelled"
            )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "placed")
        self.assertFalse(Refund.objects.filter(order=self.order).exists())

    def test_accepted_order_cannot_be_rejected(self):
        from orders.refund_service import transition_order_with_refund

        self.order.status = "accepted"
        self.order.save(update_fields=["status"])

        with self.assertRaises(RefundError):
            transition_order_with_refund(
                self.order.pk, target_status="rejected"
            )

        self.assertFalse(Refund.objects.filter(order=self.order).exists())

    def test_seller_rejection_api_reserves_refund(self):
        from unittest.mock import patch
        from rest_framework.test import APIRequestFactory, force_authenticate
        from orders.views import UpdateOrderStatusView

        request = APIRequestFactory().post(
            "/orders/test/status/",
            {"status": "rejected"},
            format="json",
        )
        force_authenticate(request, user=self.seller)

        with patch("orders.views.create_notification"):
            response = UpdateOrderStatusView.as_view()(
                request, order_id=self.order.pk
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "rejected")
        self.assertTrue(Refund.objects.filter(order=self.order).exists())

    def test_buyer_cancellation_api_reserves_refund(self):
        from unittest.mock import patch
        from rest_framework.test import APIRequestFactory, force_authenticate
        from orders.views import UpdateOrderStatusView

        request = APIRequestFactory().post(
            "/orders/test/status/",
            {"status": "cancelled"},
            format="json",
        )
        force_authenticate(request, user=self.buyer)

        with patch("orders.views.create_notification"):
            response = UpdateOrderStatusView.as_view()(
                request, order_id=self.order.pk
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)

    def test_separate_cancel_api_reserves_refund(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from orders.views import cancel_order

        request = APIRequestFactory().post(
            "/orders/test/cancel/",
            {},
            format="json",
        )
        force_authenticate(request, user=self.buyer)

        response = cancel_order(request, order_id=self.order.pk)

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)

    def test_seller_cannot_reject_accepted_order_api(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from orders.views import UpdateOrderStatusView

        self.order.status = "accepted"
        self.order.save(update_fields=["status"])

        request = APIRequestFactory().post(
            "/orders/test/status/",
            {"status": "rejected"},
            format="json",
        )
        force_authenticate(request, user=self.seller)

        response = UpdateOrderStatusView.as_view()(
            request, order_id=self.order.pk
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(Refund.objects.filter(order=self.order).exists())

    def test_other_buyer_cannot_cancel_order(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from orders.views import UpdateOrderStatusView

        other_buyer = User.objects.create(
            full_name="Another Buyer",
            phone_number="9000000803",
            user_type="buyer",
        )

        request = APIRequestFactory().post(
            "/orders/test/status/",
            {"status": "cancelled"},
            format="json",
        )
        force_authenticate(request, user=other_buyer)

        response = UpdateOrderStatusView.as_view()(
            request, order_id=self.order.pk
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Refund.objects.filter(order=self.order).exists())

    def prepare_initiated_refund(self):
        refund = self.prepare_refund()
        refund.processing_state = "initiated"
        refund.razorpay_refund_id = "rfnd_test_001"
        refund.save(update_fields=[
            "processing_state", "razorpay_refund_id"
        ])
        return refund

    def mock_refund_response(self, status="processed"):
        return {
            "id": "rfnd_test_001",
            "payment_id": "pay_refund_test_001",
            "amount": 19999,
            "currency": "INR",
            "status": status,
        }

    def test_reconcile_completed_refund(self):
        from unittest.mock import MagicMock, patch
        from orders.refund_service import reconcile_order_refund

        refund = self.prepare_initiated_refund()
        client = MagicMock()
        client.refund.fetch.return_value = self.mock_refund_response()

        with patch(
            "orders.payment_views.get_razorpay_client",
            return_value=client,
        ):
            result = reconcile_order_refund(refund.pk)

        self.assertEqual(result.processing_state, "completed")
        self.assertIsNotNone(result.completed_at)
        client.payment.refund.assert_not_called()

    def test_reconcile_pending_refund(self):
        from unittest.mock import MagicMock, patch
        from orders.refund_service import reconcile_order_refund

        refund = self.prepare_initiated_refund()
        client = MagicMock()
        client.refund.fetch.return_value = (
            self.mock_refund_response("pending")
        )

        with patch(
            "orders.payment_views.get_razorpay_client",
            return_value=client,
        ):
            result = reconcile_order_refund(refund.pk)

        self.assertEqual(result.processing_state, "initiated")
        self.assertIsNone(result.completed_at)

    def test_reconcile_failed_refund_requires_review(self):
        from unittest.mock import MagicMock, patch
        from orders.refund_service import reconcile_order_refund

        refund = self.prepare_initiated_refund()
        client = MagicMock()
        client.refund.fetch.return_value = (
            self.mock_refund_response("failed")
        )

        with patch(
            "orders.payment_views.get_razorpay_client",
            return_value=client,
        ):
            result = reconcile_order_refund(refund.pk)

        self.assertEqual(result.processing_state, "requires_review")
        self.assertIn("failed", result.failure_reason)

    def test_reconcile_mismatched_refund_is_rejected(self):
        from unittest.mock import MagicMock, patch
        from orders.refund_service import reconcile_order_refund

        refund = self.prepare_initiated_refund()
        client = MagicMock()
        response = self.mock_refund_response()
        response["amount"] = 10000
        client.refund.fetch.return_value = response

        with patch(
            "orders.payment_views.get_razorpay_client",
            return_value=client,
        ):
            with self.assertRaises(RefundError):
                reconcile_order_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "initiated")

    def test_worker_processes_reserved_refund(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        from django.test import override_settings

        refund = self.prepare_refund()
        output = StringIO()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.management.commands.process_order_refunds.process_reserved_refund"
            ) as mock_process:
                call_command(
                    "process_order_refunds",
                    execute=True,
                    stdout=output,
                )

        mock_process.assert_called_once_with(refund.pk)
        self.assertIn("initiated=1", output.getvalue())

    def test_worker_reconciles_initiated_refund(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        from django.test import override_settings

        refund = self.prepare_initiated_refund()
        output = StringIO()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.management.commands.process_order_refunds.reconcile_order_refund"
            ) as mock_reconcile:
                call_command(
                    "process_order_refunds",
                    execute=True,
                    stdout=output,
                )

        mock_reconcile.assert_called_once_with(refund.pk)
        self.assertIn("reconciled=1", output.getvalue())

    def test_worker_dry_run_preserves_reserved_refund(self):
        from io import StringIO
        from django.core.management import call_command

        refund = self.prepare_refund()
        output = StringIO()

        call_command("process_order_refunds", stdout=output)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "reserved")
        self.assertIn("DRY RUN", output.getvalue())

    def test_refund_reservation_rejects_changed_payment_reference(self):
        from orders.refund_service import transition_order_with_refund

        self.order.razorpay_payment_id = "pay_changed_before_cancel"
        self.order.save(update_fields=["razorpay_payment_id"])

        # A payment mismatch must be caught by provider verification
        # before any refund request is sent.
        with patch("orders.payment_views.get_razorpay_client") as mock_client:
            from django.test import override_settings
            from orders.refund_service import process_reserved_refund

            transition_order_with_refund(
                self.order.pk, target_status="cancelled"
            )
            refund = Refund.objects.get(order=self.order)

            mock_client.return_value.payment.fetch.return_value = {
                "id": "pay_refund_test_001",
                "order_id": "order_refund_test_001",
                "currency": "INR",
                "status": "captured",
                "captured": True,
                "amount": 19999,
                "amount_refunded": 0,
            }

            with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
                with self.assertRaises(RefundError):
                    process_reserved_refund(refund.pk)

            mock_client.return_value.payment.refund.assert_not_called()

    def test_original_checkout_amount_mismatch_blocks_cancellation(self):
        from orders.models import RazorpayCheckout
        from orders.refund_service import transition_order_with_refund

        RazorpayCheckout.objects.create(
            buyer=self.buyer,
            vendor=self.vendor,
            order=self.order,
            razorpay_order_id=self.order.razorpay_order_id,
            amount_paise=10000,
            status="confirmed",
            snapshot={},
        )

        with self.assertRaisesMessage(
            RefundError,
            "Order amount does not match original Razorpay checkout",
        ):
            transition_order_with_refund(
                self.order.pk,
                target_status="cancelled",
            )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "placed")
        self.assertFalse(
            Refund.objects.filter(order=self.order).exists()
        )

    def test_already_claimed_refund_cannot_be_processed_again(self):
        from unittest.mock import patch, MagicMock
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        refund.processing_state = "initiated"
        refund.save(update_fields=["processing_state"])

        client = MagicMock()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                with self.assertRaisesMessage(
                    RefundError,
                    "Refund is not available for initiation",
                ):
                    process_reserved_refund(refund.pk)

        client.payment.refund.assert_not_called()

    def test_stale_interrupted_refund_requires_review(self):
        from datetime import timedelta
        from io import StringIO
        from django.core.management import call_command
        from django.test import override_settings
        from django.utils import timezone

        refund = self.prepare_refund()

        Refund.objects.filter(pk=refund.pk).update(
            processing_state="initiated",
            initiated_at=timezone.now() - timedelta(minutes=20),
            razorpay_refund_id=None,
        )

        output = StringIO()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.management.commands.process_order_refunds.process_reserved_refund"
            ) as mock_process:
                call_command(
                    "process_order_refunds",
                    execute=True,
                    stdout=output,
                )

        refund.refresh_from_db()

        self.assertEqual(refund.processing_state, "requires_review")
        self.assertIn("REQUIRES REVIEW", output.getvalue())
        mock_process.assert_not_called()

    def test_recent_interrupted_refund_is_not_retried(self):
        from io import StringIO
        from django.core.management import call_command
        from django.test import override_settings
        from django.utils import timezone

        refund = self.prepare_refund()

        Refund.objects.filter(pk=refund.pk).update(
            processing_state="initiated",
            initiated_at=timezone.now(),
            razorpay_refund_id=None,
        )

        output = StringIO()

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.management.commands.process_order_refunds.process_reserved_refund"
            ) as mock_process:
                call_command(
                    "process_order_refunds",
                    execute=True,
                    stdout=output,
                )

        refund.refresh_from_db()

        self.assertEqual(refund.processing_state, "initiated")
        self.assertIn("awaiting reconciliation", output.getvalue())
        mock_process.assert_not_called()

    def test_processed_refund_updates_customer_visible_status(self):
        from unittest.mock import MagicMock
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        client.payment.fetch.return_value = self.mock_payment()
        client.payment.refund.return_value = {
            "id": "rfnd_status_test",
            "payment_id": "pay_refund_test_001",
            "amount": 19999,
            "currency": "INR",
            "status": "processed",
        }

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                process_reserved_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "completed")
        self.assertEqual(refund.status, "processed")

    def test_unknown_razorpay_status_requires_review(self):
        from unittest.mock import MagicMock
        from django.test import override_settings
        from orders.refund_service import process_reserved_refund

        refund = self.prepare_refund()
        client = MagicMock()
        client.payment.fetch.return_value = self.mock_payment()
        client.payment.refund.return_value = {
            "id": "rfnd_unknown_status",
            "payment_id": "pay_refund_test_001",
            "amount": 19999,
            "currency": "INR",
            "status": "unexpected_status",
        }

        with override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True):
            with patch(
                "orders.payment_views.get_razorpay_client",
                return_value=client,
            ):
                process_reserved_refund(refund.pk)

        refund.refresh_from_db()
        self.assertEqual(refund.processing_state, "requires_review")
        self.assertEqual(
            refund.razorpay_refund_id,
            "rfnd_unknown_status",
        )
        self.assertNotEqual(refund.status, "processed")
        self.assertIn("unexpected_status", refund.failure_reason)
