from decimal import Decimal

from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from users.deletion.worker_erasure_plan import (
    build_vendor_erasure_plan,
)


class VendorWalletBalanceTests(TestCase):

    def test_outstanding_wallet_balance_blocks_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549401",
            password="TestPassword123!",
            full_name="Vendor With Balance",
            user_type="vendor",
        )

        Vendor.objects.create(
            user=user,
            shop_name="Wallet Test Shop",
            category="supermarket",
            phone_number="9876549401",
            address="Test Street",
            town="Test Town",
            wallet_balance=Decimal("250.00"),
        )

        plan = build_vendor_erasure_plan(user)

        self.assertFalse(
            plan["eligible_for_erasure_review"],
            "Vendor with outstanding wallet balance "
            "must not be eligible for erasure.",
        )
