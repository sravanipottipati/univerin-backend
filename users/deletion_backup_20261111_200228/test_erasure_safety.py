from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request
from users.deletion.processor import (
    process_deletion_request,
    DeletionNotImplementedError,
)
from users.deletion.erasure_plan import build_buyer_erasure_plan


class BuyerErasureSafetyTests(TestCase):

    def test_no_transactions_does_not_authorize_erasure(self):
        buyer = User.objects.create_user(
            phone_number="9876548801",
            password="TestPassword123!",
            full_name="Safety Test Buyer",
            user_type="buyer",
        )

        plan = build_buyer_erasure_plan(buyer)

        self.assertEqual(
            plan["historical_orders_to_preserve"], 0
        )
        self.assertFalse(
            plan["ready_for_automatic_erasure"]
        )

        result = create_deletion_request(buyer)
        deletion_request = result["request"]

        self.assertTrue(result["created"])

        with self.assertRaises(DeletionNotImplementedError):
            process_deletion_request(deletion_request.pk)

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(
            deletion_request.status,
            "pending",
        )

    def test_processor_checks_buyer_erasure_readiness(self):
        from unittest.mock import patch

        buyer = User.objects.create_user(
            phone_number="9876548802",
            password="TestPassword123!",
            full_name="Readiness Check Buyer",
            user_type="buyer",
        )

        result = create_deletion_request(buyer)
        deletion_request = result["request"]

        with patch(
            "users.deletion.processor.build_buyer_erasure_plan",
            return_value={"ready_for_automatic_erasure": False},
        ) as mock_planner:

            with self.assertRaises(DeletionNotImplementedError):
                process_deletion_request(deletion_request.pk)

            mock_planner.assert_called_once()

            checked_user = mock_planner.call_args.args[0]
            self.assertEqual(checked_user.pk, buyer.pk)

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
