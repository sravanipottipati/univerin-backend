from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from orders.checkout_pricing import calculate_product_subtotal


class GSTVariantPricingTests(SimpleTestCase):

    def calculate(self, pricing_mode):
        vendor = SimpleNamespace(gstin="GST123")

        product = SimpleNamespace(
            price=Decimal("100.00"),
            gst_percentage=Decimal("18"),
            gst_pricing_mode=pricing_mode,
        )

        variant = SimpleNamespace(
            price=Decimal("236.00"),
            stock_quantity=10,
        )

        with (
            patch("vendors.models.Product.objects.get", return_value=product),
            patch("vendors.models.ProductVariant.objects.get", return_value=variant),
        ):
            return calculate_product_subtotal(
                vendor,
                [{
                    "product_id": "test-product",
                    "variant_id": "test-variant",
                    "quantity": 2,
                }],
            )

    def test_inclusive_variant(self):
        subtotal, items = self.calculate("inclusive")
        self.assertEqual(subtotal, Decimal("472.00"))
        self.assertEqual(items[0]["price"], Decimal("236.00"))

    def test_exclusive_variant(self):
        subtotal, items = self.calculate("exclusive")
        self.assertEqual(subtotal, Decimal("556.96"))
        self.assertEqual(items[0]["price"], Decimal("236.00"))
