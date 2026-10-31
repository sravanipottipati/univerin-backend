"""Verify Expo push receipts for previously accepted notifications."""

import logging
from datetime import timedelta

import requests
from django.utils import timezone

from orders.models import PushNotificationJob

logger = logging.getLogger(__name__)

EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
RECEIPT_BATCH_SIZE = 100


def verify_push_receipts():
    """Check a batch of sent jobs and update their receipt status."""
    now = timezone.now()
    cutoff = now - timedelta(minutes=15)
    timeout_cutoff = now - timedelta(hours=24)

    # Receipt requests older than 24 hours are no longer retried.
    # Do not resend the original push: it may already have arrived.
    PushNotificationJob.objects.filter(
        status="sent",
        updated_at__lte=timeout_cutoff,
    ).update(
        status="failed",
        last_error="Expo receipt unavailable after 24 hours",
        updated_at=now,
    )

    jobs = list(
        PushNotificationJob.objects.filter(
            status="sent",
            expo_ticket_id__gt="",
            updated_at__lte=cutoff,
        ).order_by("updated_at")[:RECEIPT_BATCH_SIZE]
    )

    if not jobs:
        return 0

    ticket_ids = [job.expo_ticket_id for job in jobs]

    try:
        response = requests.post(
            EXPO_RECEIPTS_URL,
            json={"ids": ticket_ids},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        receipts = result.get("data", {})

        if not isinstance(receipts, dict):
            raise ValueError("Unexpected Expo receipts response")

    except Exception:
        logger.exception("Unable to retrieve Expo push receipts")
        return 0

    processed = 0

    for job in jobs:
        receipt = receipts.get(job.expo_ticket_id)

        # Expo may not have generated the receipt yet.
        if not isinstance(receipt, dict):
            continue

        status = receipt.get("status")

        if status == "ok":
            updated = PushNotificationJob.objects.filter(
                pk=job.pk,
                status="sent",
                expo_ticket_id=job.expo_ticket_id,
            ).update(
                status="delivered",
                last_error="",
                updated_at=timezone.now(),
            )

        elif status == "error":
            details = receipt.get("details") or {}
            error_code = (
                details.get("error", "")
                if isinstance(details, dict)
                else ""
            )
            error_message = receipt.get("message") or error_code
            updated = PushNotificationJob.objects.filter(
                pk=job.pk,
                status="sent",
                expo_ticket_id=job.expo_ticket_id,
            ).update(
                status="failed",
                last_error=str(error_message)[:2000],
                updated_at=timezone.now(),
            )

            if updated and error_code == "DeviceNotRegistered":
                # Clear only the token associated with this failed job.
                from users.models import User

                User.objects.filter(
                    pk=job.user_id,
                    fcm_token=job.push_token,
                ).update(fcm_token="")

        else:
            continue

        processed += updated

    return processed
