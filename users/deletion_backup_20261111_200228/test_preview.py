from django.test import TestCase

from users.models import User
from users.deletion.preview import preview_account_deletion


class AccountDeletionPreviewTests(TestCase):

    def test_buyer_preview_without_related_records(self):
        user = User.objects.create_user(
            phone_number="9876544444",
            password=None,
            full_name="Preview Test Buyer",
            user_type="buyer",
        )

        result = preview_account_deletion(user)

        self.assertEqual(result["account_type"], "buyer")
        self.assertTrue(result["can_proceed"])
        self.assertTrue(result["preview_only"])
        self.assertEqual(result["blockers"], [])

        expected_counts = [
            "saved_addresses",
            "buyer_orders",
            "refund_requests",
            "razorpay_checkouts",
            "assigned_deliveries",
            "vendor_profiles",
            "delivery_partner_profiles",
            "vendor_orders",
        ]

        for key in expected_counts:
            self.assertEqual(result["record_counts"][key], 0)
