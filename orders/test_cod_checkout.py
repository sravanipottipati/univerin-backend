import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User
from vendors.models import Vendor, Product
from orders.models import Order


class CODCheckoutTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create(
            full_name="COD Test Buyer",
            phone_number="9000000101",
            user_type="buyer",
        )
        self.seller = User.objects.create(
            full_name="COD Test Seller",
            phone_number="9000000102",
            user_type="vendor",
        )
        self.vendor = Vendor.objects.create(
            user=self.seller,
            shop_name="COD Test Shop",
            category="grocery",
            phone_number="9000000102",
            address="Test Address",
            town="Test Town",
            status="approved",
            bank_account_number="1234567890",
            bank_ifsc_code="TEST0001234",
            latitude=Decimal("17.3850"),
            longitude=Decimal("78.4867"),
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            name="COD Test Product",
            price=Decimal("100.00"),
            gst_percentage=Decimal("0"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.buyer)
        self.request_id = str(uuid.uuid4())

    def payload(self):
        return {
            "vendor_id": str(self.vendor.pk),
            "client_request_id": self.request_id,
            "delivery_address": "Test Delivery Address",
            "delivery_latitude": 17.385,
            "delivery_longitude": 78.4867,
            "payment_mode": "cod",
            "items": [{
                "product_id": str(self.product.pk),
                "quantity": 1,
            }],
        }

    @patch("orders.views.create_notification")
    def test_cod_order_created(self, mock_notification):
        response = self.client.post(
            "/api/orders/place/", self.payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.first().payment_mode, "cod")

    @patch("orders.views.create_notification")
    def test_identical_retry_returns_existing_order(self, mock_notification):
        payload = self.payload()
        first = self.client.post("/api/orders/place/", payload, format="json")
        second = self.client.post("/api/orders/place/", payload, format="json")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(
            first.data["order"]["id"],
            second.data["order"]["id"],
        )

    @patch("orders.views.create_notification")
    def test_conflicting_retry_is_rejected(self, mock_notification):
        payload = self.payload()
        first = self.client.post("/api/orders/place/", payload, format="json")

        changed = self.payload()
        changed["delivery_address"] = "Different Delivery Address"
        second = self.client.post("/api/orders/place/", changed, format="json")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 409, second.data)
        self.assertEqual(Order.objects.count(), 1)
