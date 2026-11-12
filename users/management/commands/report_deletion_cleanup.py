"""
Read-only report for account deletion cleanup jobs.

Does not retry jobs, update records, or delete external assets.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset


class Command(BaseCommand):
    help = "Report account deletion cleanup jobs requiring review."

    def handle(self, *args, **options):
        now = timezone.now()

        jobs = AccountDeletionAsset.objects.filter(
            status="processing",
        ).order_by("created_at")

        count = 0

        for job in jobs:
            expired = (
                job.lease_expires_at is None
                or job.lease_expires_at <= now
            )

            uncertain = bool(job.last_error)

            if not expired and not uncertain:
                continue

            count += 1

            self.stdout.write(
                f"Job: {job.pk}\n"
                f"Attempt: {job.attempt_id}\n"
                f"Owner: {job.owner_type}\n"
                f"Field: {job.field_name}\n"
                f"Status: {job.status}\n"
                f"Lease expired: {expired}\n"
                f"Storage outcome uncertain: {uncertain}\n"
                f"Action: ADMINISTRATOR RECONCILIATION REQUIRED\n"
                f"{'-' * 45}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup jobs requiring review: {count}"
            )
        )
