"""
Read-only account deletion preview.

Counts related records without deleting or modifying data.
"""

from django.apps import apps

from users.deletion.retention import assess_account_deletion


def preview_account_deletion(user):
    assessment = assess_account_deletion(user)

    Address = apps.get_model("users", "Address")
    Order = apps.get_model("orders", "Order")
    Refund = apps.get_model("orders", "Refund")
    RazorpayCheckout = apps.get_model("orders", "RazorpayCheckout")
    Vendor = apps.get_model("vendors", "Vendor")
    DeliveryPartner = apps.get_model(
        "delivery_partner", "DeliveryPartner"
    )

    counts = {
        "saved_addresses": Address.objects.filter(user=user).count(),
        "buyer_orders": Order.objects.filter(buyer=user).count(),
        "refund_requests": Refund.objects.filter(
            requested_by=user
        ).count(),
        "razorpay_checkouts": RazorpayCheckout.objects.filter(
            buyer=user
        ).count(),
        "assigned_deliveries": Order.objects.filter(
            delivery_partner=user
        ).count(),
        "vendor_profiles": Vendor.objects.filter(user=user).count(),
        "delivery_partner_profiles": DeliveryPartner.objects.filter(
            user=user
        ).count(),
    }

    vendor = Vendor.objects.filter(user=user).first()

    if vendor:
        counts["vendor_orders"] = Order.objects.filter(
            vendor=vendor
        ).count()
    else:
        counts["vendor_orders"] = 0

    return {
        "account_type": user.user_type,
        "can_proceed": assessment.can_proceed,
        "blockers": assessment.blockers,
        "record_counts": counts,
        "retained_records": assessment.retained_records,
        "personal_data_categories": assessment.personal_data_categories,
        "preview_only": True,
    }
