"""
Read-only deletion plans for vendors and delivery partners.

No database or Cloudinary changes are performed.
"""

from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner


def build_vendor_erasure_plan(user):
    if user.user_type != "vendor":
        raise ValueError("Vendor account required.")

    vendor = Vendor.objects.filter(user=user).first()

    if vendor is None:
        return {
            "account_type": "vendor",
            "eligible_for_erasure_review": False,
            "blockers": ["Vendor profile missing."],
        }

    return {
        "account_type": "vendor",
        "vendor_id": str(vendor.pk),
        "historical_orders": vendor.orders.count(),
        "checkout_records": vendor.razorpay_checkouts.count(),
        "wallet_transactions": vendor.transactions.count(),
        "products": vendor.products.count(),
        "reviews": vendor.reviews.count(),
        "has_bank_details": any([
            vendor.bank_account_name,
            vendor.bank_account_number,
            vendor.bank_ifsc_code,
            vendor.bank_name,
        ]),
        "has_tax_identifiers": bool(vendor.gstin or vendor.pan),
        "has_uploaded_documents": bool(
            vendor.fssai_certificate or vendor.banner_image
        ),
        "eligible_for_erasure_review": not any([
            vendor.orders.exists(),
            vendor.razorpay_checkouts.exists(),
            vendor.transactions.exists(),
        vendor.wallet_balance != 0,
            vendor.reviews.exists(),
            vendor.products.exists(),
            vendor.cart_items.exists(),
            bool(vendor.fssai_certificate),
            bool(vendor.banner_image),
            bool(user.profile_photo),
            user.orders.exists(),
            user.razorpay_checkouts.exists(),
            user.deliveries.exists(),
            user.refunds.exists(),
            user.approved_refunds.exists(),
            user.returnrequest_set.exists(),
            user.reviews.exists(),
            user.addresses.exists(),
            user.cart_items.exists(),
            user.wishlist.exists(),
        ]),
        "blockers": [
            "Vendor activity, related records, or uploaded files require review."
        ],
    }


def build_delivery_partner_erasure_plan(user):
    if user.user_type != "delivery_partner":
        raise ValueError("Delivery partner account required.")

    partner = DeliveryPartner.objects.filter(user=user).first()

    if partner is None:
        return {
            "account_type": "delivery_partner",
            "eligible_for_erasure_review": False,
            "blockers": ["Delivery partner profile missing."],
        }

    return {
        "account_type": "delivery_partner",
        "delivery_partner_id": str(partner.pk),
        "historical_deliveries": user.deliveries.count(),
        "delivery_offers": user.delivery_offers.count(),
        "has_kyc_identifiers": any([
            partner.aadhaar_number,
            partner.pan_number,
            partner.driving_licence_number,
        ]),
        "has_kyc_documents": any([
            partner.aadhaar_document,
            partner.pan_document,
            partner.driving_licence_document,
            partner.selfie_photo,
        ]),
        "has_location_data": (
            partner.current_latitude is not None
            or partner.current_longitude is not None
        ),
        "eligible_for_erasure_review": not any([
            user.deliveries.exists(),
            user.delivery_offers.exists(),
            user.orders.exists(),
            user.razorpay_checkouts.exists(),
            user.refunds.exists(),
            user.approved_refunds.exists(),
            user.returnrequest_set.exists(),
            user.reviews.exists(),
            user.addresses.exists(),
            user.cart_items.exists(),
            user.wishlist.exists(),
            bool(partner.aadhaar_document),
            bool(partner.pan_document),
            bool(partner.driving_licence_document),
            bool(partner.selfie_photo),
            bool(user.profile_photo),
        ]),
        "blockers": [
            "Delivery history or uploaded documents require review."
        ],
    }
