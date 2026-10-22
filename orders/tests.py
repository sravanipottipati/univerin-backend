from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.models import Order, Notification
from orders.views import UpdateOrderStatusView
from vendors.models import Vendor
from wallet.models import WalletTransaction


class SellerAcceptanceDispatchTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.buyer = User.objects.create_user(
            phone_number="9000000701",
            full_name="Dispatch Regression Buyer",
            user_type="buyer",
        )

        self.seller = User.objects.create_user(
            phone_number="9000000702",
            full_name="Dispatch Regression Seller",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="Dispatch Regression Shop",
            category="supermarket",
            phone_number="9000000702",
            address="Test Shop Address",
            town="Test Town",
            platform_fee=Decimal("10.00"),
        )

        self.order = Order.objects.create(
            order_number="UNI-REG-0701",
            buyer=self.buyer,
            vendor=self.vendor,
            status="placed",
            total_amount=Decimal("250.00"),
            platform_fee=Decimal("10.00"),
            delivery_address="Test Buyer Address",
            dp_status="unassigned",
        )

        self.factory = APIRequestFactory()

    def update_status(self, new_status="accepted"):
        request = self.factory.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": new_status},
            format="json",
        )
        force_authenticate(request, user=self.seller)

        return UpdateOrderStatusView.as_view()(
            request,
            order_id=self.order.id,
        )

    @patch("orders.views.create_next_delivery_offer")
    def test_first_acceptance_starts_dispatch_and_preserves_workflow(
        self, mock_dispatch
    ):
        response = self.update_status("accepted")

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "accepted")

        mock_dispatch.assert_called_once_with(self.order.id)

        transaction = WalletTransaction.objects.get(order=self.order)
        self.assertEqual(transaction.transaction_type, "debit")
        self.assertEqual(transaction.amount, Decimal("10.00"))
        self.assertEqual(transaction.status, "pending")

        self.assertTrue(
            Notification.objects.filter(
                user=self.buyer,
                order=self.order,
                type="order_accepted",
            ).exists()
        )

    @patch("orders.views.create_next_delivery_offer")
    def test_repeated_acceptance_does_not_restart_dispatch(
        self, mock_dispatch
    ):
        first_response = self.update_status("accepted")
        self.assertEqual(first_response.status_code, 200)

        second_response = self.update_status("accepted")
        self.assertEqual(second_response.status_code, 200)

        mock_dispatch.assert_called_once_with(self.order.id)

        self.assertEqual(
            WalletTransaction.objects.filter(order=self.order).count(),
            1,
        )

    def test_seller_cannot_bypass_delivery_partner_workflow(self):
        for status in ("dispatched", "delivered"):
            with self.subTest(status=status):
                response = self.update_status(status)

                self.assertEqual(response.status_code, 400)

                self.order.refresh_from_db()
                self.assertEqual(self.order.status, "placed")

                self.assertFalse(
                    Notification.objects.filter(
                        order=self.order,
                        type=f"order_{status}",
                    ).exists()
                )
