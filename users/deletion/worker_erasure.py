"""
Conservative vendor and delivery partner erasure.

Must only be invoked by the authorized deletion processor.
Accounts with historical records or uploaded files requiring review
are not eligible.
"""

from django.db import transaction
from django.utils import timezone

from users.deletion.worker_erasure_plan import (
    build_vendor_erasure_plan,
    build_delivery_partner_erasure_plan,
)


class WorkerErasureNotReadyError(Exception):
    pass


def _erase_common_user_data(user):
    if user.is_staff or user.is_admin or user.is_deleted:
        raise WorkerErasureNotReadyError(
            "Protected or previously deleted account."
        )

    if user.profile_photo and user.profile_photo.name:
        raise WorkerErasureNotReadyError(
            "Profile photo requires external cleanup."
        )

    user.addresses.all().delete()
    user.cart_items.all().delete()
    user.wishlist.all().delete()
    user.notifications.all().delete()
    user.reset_otps.all().delete()
    user.push_notification_jobs.all().delete()

    user.full_name = "Deleted User"
    user.phone_number = None
    user.email = None
    user.fcm_token = None
    user.town = None
    user.profile_photo = None

    user.set_unusable_password()
    user.is_active = False
    user.is_deleted = True
    user.deleted_at = timezone.now()
    user.save()


@transaction.atomic
def erase_vendor_personal_data(user):
    if user.user_type != "vendor":
        raise ValueError("Vendor account required.")

    plan = build_vendor_erasure_plan(user)

    if not plan["eligible_for_erasure_review"]:
        raise WorkerErasureNotReadyError(
            "; ".join(plan["blockers"])
        )

    vendor = user.vendor

    vendor.bank_account_name = None
    vendor.bank_account_number = None
    vendor.bank_ifsc_code = None
    vendor.bank_name = None

    vendor.shop_name = "Deleted Vendor"
    vendor.description = None
    vendor.phone_number = ""
    vendor.address = ""
    vendor.town = ""
    vendor.state = ""
    vendor.gstin = None
    vendor.pan = None
    vendor.fssai_number = None
    vendor.latitude = None
    vendor.longitude = None
    vendor.is_open = False
    vendor.status = "rejected"

    vendor.save()

    _erase_common_user_data(user)

    return user


@transaction.atomic
def erase_delivery_partner_personal_data(user):
    if user.user_type != "delivery_partner":
        raise ValueError("Delivery partner account required.")

    plan = build_delivery_partner_erasure_plan(user)

    if not plan["eligible_for_erasure_review"]:
        raise WorkerErasureNotReadyError(
            "; ".join(plan["blockers"])
        )

    partner = user.delivery_partner

    partner.vehicle_type = None
    partner.vehicle_number = None

    partner.aadhaar_number = None
    partner.pan_number = None
    partner.driving_licence_number = None

    partner.rejection_reason = None
    partner.is_online = False
    partner.current_latitude = None
    partner.current_longitude = None
    partner.location_updated_at = None
    partner.status = "rejected"

    partner.save()

    _erase_common_user_data(user)

    return user
