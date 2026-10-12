from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class ExpirationCommandTests(SimpleTestCase):

    @patch(
        "orders.management.commands.expire_delivery_offers.expire_due_delivery_offers"
    )
    def test_command_processes_expired_offers(self, mock_expire):
        mock_expire.return_value = 3
        output = StringIO()

        call_command("expire_delivery_offers", stdout=output)

        mock_expire.assert_called_once_with()
        self.assertIn(
            "Processed 3 expired delivery offer(s).",
            output.getvalue(),
        )
