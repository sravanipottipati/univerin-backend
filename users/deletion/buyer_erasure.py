"""
Buyer personal-data erasure.

Only buyers with no transaction or review history are eligible.
This function must be called inside the authorized deletion processor.
"""

from django.db import transaction
from django.utils import timezone
from django.core.files.storage import default_storage

from orders.models import Order, RazorpayCheckout, ReturnRequest, Refund


class BuyerErasureNotReadyError(Exception):
    """Buyer cannot safely be erased yet."""


@transaction.atomic
def erase_buyer_personal_data(user):
    if user.user_type != "buyer":
        raise ValueError("Buyer erasure requires a buyer account.")

    if user.is_staff or user.is_admin or user.is_deleted:
        raise BuyerErasureNotReadyError(
            "Protected or previously deleted account."
        )

    if (
        Order.objects.filter(buyer=user).exists()
        or Order.objects.filter(delivery_partner=user).exists()
        or RazorpayCheckout.objects.filter(buyer=user).exists()
        or Refund.objects.filter(requested_by=user).exists()
        or Refund.objects.filter(approved_by=user).exists()
        or ReturnRequest.objects.filter(buyer=user).exists()
        or user.reviews.exists()
    ):
        raise BuyerErasureNotReadyError(
            "Account has historical records requiring retention review."
        )

    # Remove the externally stored profile photo before clearing its reference.
    # A storage failure must stop account erasure.
    if user.profile_photo and user.profile_photo.name:
        photo_name = user.profile_photo.name
        try:
            default_storage.delete(photo_name)
        except Exception as exc:
            raise BuyerErasureNotReadyError(
                "Profile photo cleanup failed. Account erasure stopped."
            ) from exc

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

    return user
