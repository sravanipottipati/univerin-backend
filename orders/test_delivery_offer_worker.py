from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class DeliveryOfferWorkerTests(SimpleTestCase):

    @patch(
        "orders.management.commands.run_delivery_offer_worker.time.sleep",
        side_effect=KeyboardInterrupt,
    )
    @patch(
        "orders.management.commands.run_delivery_offer_worker.close_old_connections"
    )
    @patch(
        "orders.management.commands.run_delivery_offer_worker.expire_due_delivery_offers",
        return_value=2,
    )
    def test_worker_processes_offers_and_stops_safely(
        self, mock_expire, mock_close, mock_sleep
    ):
        output = StringIO()

        call_command(
            "run_delivery_offer_worker",
            stdout=output,
        )

        mock_expire.assert_called_once_with()
        mock_sleep.assert_called_once_with(5)
        self.assertEqual(mock_close.call_count, 2)

        self.assertIn(
            "Delivery offer expiration worker started.",
            output.getvalue(),
        )
        self.assertIn(
            "Expired 2 delivery offer(s).",
            output.getvalue(),
        )
        self.assertIn(
            "Delivery offer expiration worker stopped.",
            output.getvalue(),
        )
