from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from orders.checkout_pricing import calculate_product_subtotal


class GSTInclusivePricingTests(SimpleTestCase):

    def calculate(self, price, gst_rate, gstin, quantity=1):
        vendor = SimpleNamespace(gstin=gstin)

        product = SimpleNamespace(
            price=Decimal(price),
            gst_percentage=Decimal(gst_rate),
            gst_pricing_mode="inclusive",
        )

        with patch(
            "vendors.models.Product.objects.get",
            return_value=product,
        ):
            return calculate_product_subtotal(
                vendor,
                [{"product_id": "test-product", "quantity": quantity}],
            )

    def test_inclusive_price_does_not_add_gst_again(self):
        subtotal, items = self.calculate("118.00", "18", "GST123")

        self.assertEqual(subtotal, Decimal("118.00"))
        self.assertEqual(items[0]["line_total"], Decimal("118.00"))
        self.assertEqual(items[0]["gst_rate"], Decimal("18"))

    def test_inclusive_price_multiple_quantities(self):
        subtotal, items = self.calculate("118.00", "18", "GST123", 3)

        self.assertEqual(subtotal, Decimal("354.00"))
        self.assertEqual(items[0]["quantity"], 3)

    def test_non_gst_seller_does_not_add_tax(self):
        subtotal, items = self.calculate("118.00", "18", "", 1)

        self.assertEqual(subtotal, Decimal("118.00"))
        self.assertEqual(items[0]["gst_rate"], Decimal("0"))
