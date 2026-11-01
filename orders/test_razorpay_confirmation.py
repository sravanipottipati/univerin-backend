from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from users.models import User
from vendors.models import Vendor, Product
from orders.models import Order, OrderItem, RazorpayCheckout
from orders.payment_views import _create_order_from_verified_checkout


class RazorpayConfirmationTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create(
            full_name="Test Buyer",
            phone_number="9000000001",
            user_type="buyer",
        )
        self.seller = User.objects.create(
            full_name="Test Seller",
            phone_number="9000000002",
            user_type="vendor",
        )
        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="Test Shop",
            category="grocery",
            phone_number="9000000002",
            address="Test Address",
            town="Test Town",
            status="approved",
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            name="Test Product",
            price=Decimal("100.00"),
            gst_percentage=Decimal("5.00"),
            gst_pricing_mode="inclusive",
        )

        self.payment_order_id = "order_test_123"
        self.payment_id = "pay_test_123"

        self.checkout = RazorpayCheckout.objects.create(
            buyer=self.buyer,
            vendor=self.vendor,
            razorpay_order_id=self.payment_order_id,
            amount_paise=11180,
            status="created",
            snapshot={
                "vendor_id": str(self.vendor.pk),
                "subtotal": "100.00",
                "platform_fee": "10.00",
                "delivery_fee_incl_gst": "0.00",
                "total": "111.80",
                "delivery_address": "Test Delivery Address",
                "delivery_latitude": 17.385,
                "delivery_longitude": 78.4867,
                "items": [{
                    "product_id": str(self.product.pk),
                    "variant_id": None,
                    "quantity": 1,
                    "price": "100.00",
                    "gst_rate": "5.00",
                }],
            },
        )

    def confirm(self, payment_id=None):
        return _create_order_from_verified_checkout(
            self.checkout,
            self.payment_order_id,
            payment_id or self.payment_id,
            self.buyer,
        )

    @patch("orders.views.create_notification")
    def test_payment_creates_order_with_gst_snapshot(self, mock_notification):
        response = self.confirm()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

        order = Order.objects.get()
        item = OrderItem.objects.get()

        self.assertEqual(order.payment_mode, "online")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.razorpay_payment_id, self.payment_id)
        self.assertEqual(order.total_amount, Decimal("111.80"))
        self.assertEqual(item.gst_rate_at_purchase, Decimal("5.00"))
        self.assertEqual(item.gst_pricing_mode_at_purchase, "inclusive")

        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, "confirmed")
        self.assertEqual(self.checkout.order_id, order.pk)

    @patch("orders.views.create_notification")
    def test_retry_does_not_create_duplicate_order(self, mock_notification):
        first = self.confirm()
        second = self.confirm()

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    @patch("orders.views.create_notification")
    def test_mismatched_payment_id_is_rejected(self, mock_notification):
        first = self.confirm()
        second = self.confirm("pay_different_456")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 409, second.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)
