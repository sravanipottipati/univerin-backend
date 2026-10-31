"""Database-backed queue for UNIVERIN Expo push notifications."""

import logging

from django.db import transaction

from orders.models import PushNotificationJob

logger = logging.getLogger(__name__)


def queue_push_notification(
    user,
    title,
    message,
    notification=None,
    delivery_offer=None,
    payload=None,
):
    """
    Queue a push notification without making an HTTP request.

    Returns the queued job, or None if the user has no push token.
    """
    push_token = (getattr(user, "fcm_token", None) or "").strip()

    if not push_token:
        logger.info(
            "Skipping push queue: user %s has no registered token",
            user.pk,
        )
        return None

    data = dict(payload or {})

    if delivery_offer is not None:
        data["offer_id"] = str(delivery_offer.pk)
        data["order_id"] = str(delivery_offer.order_id)
        data["type"] = "delivery_offer"

    if delivery_offer is not None:
        job, created = PushNotificationJob.objects.get_or_create(
            delivery_offer=delivery_offer,
            defaults={
                "user": user,
                "notification": notification,
                "push_token": push_token,
                "title": title,
                "message": message,
                "payload": data,
            },
        )

        if not created:
            logger.info(
                "Push job already exists for delivery offer %s",
                delivery_offer.pk,
            )

        return job

    return PushNotificationJob.objects.create(
        user=user,
        notification=notification,
        push_token=push_token,
        title=title,
        message=message,
        payload=data,
    )
