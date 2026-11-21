from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


class RefundWorkerTests(TestCase):

    @patch("orders.management.commands.process_order_refunds.process_reserved_refund")
    @patch("orders.management.commands.process_order_refunds.reconcile_order_refund")
    def test_dry_run_does_not_call_razorpay(
        self, mock_reconcile, mock_process
    ):
        output = StringIO()

        call_command("process_order_refunds", stdout=output)

        self.assertIn("dry_run=True", output.getvalue())
        mock_process.assert_not_called()
        mock_reconcile.assert_not_called()

    @override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=False)
    def test_execute_blocked_when_disabled(self):
        with self.assertRaises(CommandError):
            call_command("process_order_refunds", execute=True)

    def test_invalid_limit_rejected(self):
        with self.assertRaises(CommandError):
            call_command("process_order_refunds", limit=0)

        with self.assertRaises(CommandError):
            call_command("process_order_refunds", limit=101)

    @override_settings(RAZORPAY_AUTO_REFUNDS_ENABLED=True)
    @patch("orders.management.commands.process_order_refunds.process_reserved_refund")
    def test_empty_worker_execution(self, mock_process):
        output = StringIO()

        call_command(
            "process_order_refunds",
            execute=True,
            stdout=output,
        )

        self.assertIn("inspected=0", output.getvalue())
        mock_process.assert_not_called()
