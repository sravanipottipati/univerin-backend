"""
Read-only buyer account erasure planning.

This module does not modify or delete database records.
"""

from orders.models import Order, RazorpayCheckout
from users.models import Address


def build_buyer_erasure_plan(user):
    if user.user_type != "buyer":
        raise ValueError("Buyer erasure plan requires a buyer account.")

    orders = Order.objects.filter(buyer=user)
    checkouts = RazorpayCheckout.objects.filter(buyer=user)

    return {
        "account_type": "buyer",
        "user_id": str(user.pk),
        "profile_fields_to_clear": [
            "full_name",
            "phone_number",
            "email",
            "password",
            "fcm_token",
            "town",
            "profile_photo",
        ],
        "saved_addresses_to_delete": Address.objects.filter(
            user=user
        ).count(),
        "cart_items_to_delete": user.cart_items.count(),
        "wishlist_items_to_delete": user.wishlist.count(),
        "notifications_to_review": user.notifications.count(),
        "reviews_to_review": user.reviews.count(),
        "password_reset_otps_to_delete": user.reset_otps.count(),
        "refunds_to_review": user.refunds.count(),
        "return_requests_to_review": (
            __import__(
                "orders.models",
                fromlist=["ReturnRequest"]
            ).ReturnRequest.objects.filter(buyer=user).count()
        ),
        "historical_orders_to_preserve": orders.count(),
        "orders_with_delivery_addresses_to_review": orders.exclude(
            delivery_address=""
        ).count(),
        "orders_with_coordinates_to_review": orders.filter(
            delivery_latitude__isnull=False
        ).count() + orders.filter(
            delivery_longitude__isnull=False
        ).exclude(
            delivery_latitude__isnull=False
        ).count(),
        "checkout_snapshots_to_review": checkouts.count(),
        "payment_records_to_preserve": checkouts.count(),
        "requires_retention_review": (
            orders.exists() or checkouts.exists()
        ),
        # Automatic erasure remains disabled until all related
        # records, external files, and retention rules are covered.
        "ready_for_automatic_erasure": False,
    }
