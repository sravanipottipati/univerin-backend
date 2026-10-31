"""Welcome notifications for newly registered UNIVERIN users."""

from django.db import transaction
from orders.models import Notification

WELCOME_MESSAGES = {
    "buyer": (
        "Welcome to UNIVERIN!",
        "Discover local shops and start shopping."
    ),
    "vendor": (
        "Welcome to UNIVERIN!",
        "Set up your shop and start reaching local customers."
    ),
    "delivery_partner": (
        "Welcome to UNIVERIN!",
        "Complete your onboarding to start receiving delivery opportunities."
    ),
}


def create_welcome_notification(user):
    """Create one in-app welcome notification for a new user."""
    title, message = WELCOME_MESSAGES.get(
        user.user_type,
        WELCOME_MESSAGES["buyer"],
    )

    with transaction.atomic():
        # Lock the user row to prevent duplicate welcome notifications.
        type(user).objects.select_for_update().get(pk=user.pk)

        notification, created = Notification.objects.get_or_create(
            user=user,
            type="welcome",
            defaults={
                "title": title,
                "message": message,
            },
        )

    return notification, created
