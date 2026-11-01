"""Trusted checkout pricing helpers for UNIVERIN."""

from decimal import Decimal
from vendors.serializers import calculate_distance


PLATFORM_FEE = Decimal("10.00")
PLATFORM_FEE_WITH_GST = Decimal("11.80")
MAX_DELIVERY_DISTANCE_KM = Decimal("6.0")


def calculate_delivery_fee(vendor, latitude, longitude, subtotal):
    """Return the delivery fee including GST, using trusted vendor coordinates."""
    if (
        latitude is None
        or longitude is None
        or vendor.latitude is None
        or vendor.longitude is None
    ):
        raise ValueError("Valid delivery coordinates are required.")

    buyer_lat = float(latitude)
    buyer_lng = float(longitude)

    if not (-90 <= buyer_lat <= 90 and -180 <= buyer_lng <= 180):
        raise ValueError("Delivery coordinates are out of range.")

    distance = Decimal(str(calculate_distance(
        buyer_lat, buyer_lng,
        float(vendor.latitude), float(vendor.longitude)
    )))

    if distance > MAX_DELIVERY_DISTANCE_KM:
        raise ValueError("Delivery address is outside the 6 km service area.")

    minimum_order = vendor.min_order if vendor.min_order is not None else Decimal("100")

    if minimum_order > 0 and subtotal >= minimum_order:
        return Decimal("0.00")

    if distance <= Decimal("2.0"):
        return Decimal("25.00")
    if distance <= Decimal("4.0"):
        return Decimal("35.00")
    return Decimal("45.00")


def calculate_product_subtotal(vendor, items):
    """Calculate trusted product totals and return validated order items."""
    from vendors.models import Product, ProductVariant

    if not isinstance(items, list) or not items:
        raise ValueError("Checkout must contain at least one product.")

    subtotal = Decimal("0.00")
    validated_items = []
    apply_gst = bool(vendor.gstin and vendor.gstin.strip())

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid checkout item.")

        try:
            quantity = int(item["quantity"])
            if isinstance(item["quantity"], bool) or str(item["quantity"]) != str(quantity):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ValueError("Invalid product quantity.")

        if quantity <= 0:
            raise ValueError("Product quantity must be positive.")

        try:
            product = Product.objects.get(
                id=item["product_id"],
                vendor=vendor,
                is_available=True,
                is_draft=False,
            )
        except (Product.DoesNotExist, KeyError, TypeError, ValueError):
            raise ValueError("Product is unavailable or does not belong to this shop.")

        variant = None
        price = product.price

        if item.get("variant_id"):
            try:
                variant = ProductVariant.objects.get(
                    id=item["variant_id"],
                    product=product,
                    is_available=True,
                )
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                raise ValueError("Selected product variant is unavailable.")

            if quantity > variant.stock_quantity:
                raise ValueError("Insufficient stock for selected variant.")

            price = variant.price

        if price < 0:
            raise ValueError("Invalid product price.")

        gst_rate = product.gst_percentage if apply_gst else Decimal("0")
        if gst_rate < 0 or gst_rate > 100:
            raise ValueError("Invalid product GST percentage.")

        pricing_mode = getattr(product, "gst_pricing_mode", "exclusive")

        if pricing_mode not in ("exclusive", "inclusive"):
            raise ValueError("Invalid product GST pricing mode.")

        if pricing_mode == "inclusive":
            line_total = (price * quantity).quantize(Decimal("0.01"))
        else:
            line_total = (
                price * quantity * (Decimal("1") + gst_rate / Decimal("100"))
            ).quantize(Decimal("0.01"))

        subtotal += line_total
        validated_items.append({
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "price": price,
            "gst_rate": gst_rate,
            "line_total": line_total,
        })

    return subtotal, validated_items


def calculate_checkout_total(vendor, items, latitude, longitude):
    """Calculate the authoritative checkout total for online payment."""
    from decimal import ROUND_HALF_UP

    subtotal, validated_items = calculate_product_subtotal(vendor, items)

    delivery_fee_incl_gst = calculate_delivery_fee(
        vendor, latitude, longitude, subtotal
    )

    total_before_rounding = (
        subtotal + delivery_fee_incl_gst + PLATFORM_FEE_WITH_GST
    )

    # Match the Buyer's whole-rupee Razorpay checkout amount.
    total = total_before_rounding.quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )

    if total <= 0:
        raise ValueError("Checkout amount must be positive.")

    amount_paise = int(total * 100)

    return {
        "subtotal": subtotal,
        "items": validated_items,
        "delivery_fee_incl_gst": delivery_fee_incl_gst,
        "platform_fee": PLATFORM_FEE,
        "platform_fee_with_gst": PLATFORM_FEE_WITH_GST,
        "total_before_rounding": total_before_rounding,
        "total": total,
        "amount_paise": amount_paise,
    }


def calculate_inclusive_gst(price, gst_rate):
    """Split a GST-inclusive price into taxable value and GST."""
    from decimal import ROUND_HALF_UP

    price = Decimal(str(price))
    gst_rate = Decimal(str(gst_rate))

    if price < 0:
        raise ValueError("Invalid product price.")
    if gst_rate < 0 or gst_rate > 100:
        raise ValueError("Invalid product GST percentage.")

    taxable = (
        price * Decimal("100") / (Decimal("100") + gst_rate)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    gst_amount = price - taxable

    return {
        "inclusive_total": price,
        "taxable_value": taxable,
        "gst_amount": gst_amount,
        "gst_rate": gst_rate,
    }
