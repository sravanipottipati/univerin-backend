"""Background worker for queued UNIVERIN Expo push notifications."""

import logging
import time
from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone

from orders.models import PushNotificationJob

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
MAX_ATTEMPTS = 5
PROCESSING_TIMEOUT_SECONDS = 60


def recover_stale_jobs():
    """Recover jobs abandoned by a crashed worker."""
    cutoff = timezone.now() - timedelta(
        seconds=PROCESSING_TIMEOUT_SECONDS
    )

    stale_jobs = PushNotificationJob.objects.filter(
        status="processing",
        updated_at__lte=cutoff,
    )

    stale_jobs.filter(
        attempts__gte=MAX_ATTEMPTS
    ).update(
        status="failed",
        last_error="Worker stopped after maximum attempts",
    )

    return stale_jobs.filter(
        attempts__lt=MAX_ATTEMPTS
    ).update(
        status="pending",
        next_attempt_at=timezone.now(),
        last_error="Recovered after worker interruption",
    )


def claim_job():
    """Atomically claim one eligible job."""
    with transaction.atomic():
        job = (
            PushNotificationJob.objects
            .select_for_update(skip_locked=True)
            .filter(
                status="pending",
                next_attempt_at__lte=timezone.now(),
            )
            .order_by("created_at")
            .first()
        )

        if job is None:
            return None

        job.status = "processing"
        job.attempts += 1
        job.save(update_fields=["status", "attempts", "updated_at"])
        return job.pk


def save_if_current(job, **changes):
    """Update only if this worker still owns the processing attempt."""
    changes["updated_at"] = timezone.now()
    return PushNotificationJob.objects.filter(
        pk=job.pk,
        status="processing",
        attempts=job.attempts,
    ).update(**changes) == 1


def process_job(job_id):
    job = (
        PushNotificationJob.objects
        .select_related("delivery_offer", "user")
        .get(pk=job_id)
    )

    if job.delivery_offer_id:
        offer = job.delivery_offer

        if (
            offer is None
            or offer.status != "pending"
            or offer.expires_at <= timezone.now()
        ):
            save_if_current(
                job,
                status="failed",
                last_error="Delivery offer expired or is no longer pending",
            )
            return

    # Do not send to a token that has since been replaced or removed.
    if not job.push_token or job.push_token != (job.user.fcm_token or ""):
        save_if_current(
            job,
            status="failed",
            last_error="Push token is no longer registered for this user",
        )
        return

    payload = {
        "to": job.push_token,
        "title": job.title,
        "body": job.message,
        "sound": "default",
        "data": job.payload or {},
    }

    # Confirm ownership before making the external Expo request.
    # A recovered job may already belong to a newer worker.
    still_owned = PushNotificationJob.objects.filter(
        pk=job.pk,
        status="processing",
        attempts=job.attempts,
    ).exists()

    if not still_owned:
        logger.info(
            "Skipping push job %s: processing ownership changed",
            job.pk,
        )
        return

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=5,
        )
        response.raise_for_status()

        result = response.json()
        ticket = result.get("data", {})

        if isinstance(ticket, list):
            ticket = ticket[0] if ticket else {}

        if not isinstance(ticket, dict):
            raise ValueError("Unexpected Expo push response")

        if ticket.get("status") != "ok":
            error_message = (
                ticket.get("message")
                or str(ticket.get("details", {}))
                or "Expo rejected push notification"
            )
            raise ValueError(error_message)

        save_if_current(
            job,
            status="sent",
            expo_ticket_id=ticket.get("id", ""),
            last_error="",
        )

        logger.info("Push job %s accepted by Expo", job.pk)

    except Exception as exc:
        job.last_error = str(exc)[:2000]

        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
        else:
            job.status = "pending"
            delay_seconds = min(30 * (2 ** (job.attempts - 1)), 300)
            job.next_attempt_at = timezone.now() + timedelta(
                seconds=delay_seconds
            )

        save_if_current(
            job,
            status=job.status,
            last_error=job.last_error,
            next_attempt_at=job.next_attempt_at,
        )
        logger.warning("Push job %s failed: %s", job.pk, exc)


class Command(BaseCommand):
    help = "Continuously send queued Expo push notifications."

    def handle(self, *args, **options):
        self.stdout.write("UNIVERIN push notification worker started.")

        try:
            while True:
                close_old_connections()

                try:
                    recover_stale_jobs()
                    job_id = claim_job()

                    if job_id:
                        process_job(job_id)
                    else:
                        time.sleep(2)

                except Exception:
                    logger.exception("Unexpected push worker error")
                    time.sleep(2)

                finally:
                    close_old_connections()

        except KeyboardInterrupt:
            self.stdout.write("Push notification worker stopped.")
