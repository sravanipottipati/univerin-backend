"""Canonical request fingerprints for COD checkout retries."""

import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation


def _canonical_uuid(value):
    return str(uuid.UUID(str(value)))


def _canonical_coordinate(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid delivery coordinate")

    if not number.is_finite():
        raise ValueError("Invalid delivery coordinate")

    return format(number.normalize(), "f")


def cod_request_fingerprint(data):
    """Hash checkout intent, excluding untrusted client prices and totals."""
    items = []

    for item in data["items"]:
        quantity = item["quantity"]

        if isinstance(quantity, bool):
            raise ValueError("Invalid item quantity")

        try:
            number = Decimal(str(quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Invalid item quantity")

        if (
            not number.is_finite()
            or number <= 0
            or number != number.to_integral_value()
        ):
            raise ValueError("Invalid item quantity")

        quantity = int(number)

        items.append({
            "product_id": _canonical_uuid(item["product_id"]),
            "variant_id": (
                _canonical_uuid(item["variant_id"])
                if item.get("variant_id")
                else None
            ),
            "quantity": quantity,
        })

    items.sort(key=lambda item: (
        item["product_id"],
        item["variant_id"] or "",
        item["quantity"],
    ))

    canonical = {
        "version": 1,
        "vendor_id": _canonical_uuid(data["vendor_id"]),
        "payment_mode": data.get("payment_mode", "cod"),
        "items": items,
        "delivery_address": data["delivery_address"],
        "delivery_latitude": _canonical_coordinate(
            data.get("delivery_latitude")
        ),
        "delivery_longitude": _canonical_coordinate(
            data.get("delivery_longitude")
        ),
        "instructions": data.get("instructions", ""),
    }

    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()
