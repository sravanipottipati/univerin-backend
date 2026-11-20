"""
Read-only preview of queued account deletion asset cleanup.

Never claims jobs, modifies records, or contacts external storage.
"""

from django.core.management.base import BaseCommand

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_worker import (
    inspect_cleanup_job,
    AssetCleanupBlockedError,
)


class Command(BaseCommand):
    help = "Preview queued account deletion asset cleanup safely."

    def handle(self, *args, **options):
        jobs = AccountDeletionAsset.objects.filter(
            status__in=["pending", "failed"],
        ).order_by("created_at")

        ready = 0
        blocked = 0

        for job in jobs.iterator():
            try:
                inspect_cleanup_job(job.pk)
            except AssetCleanupBlockedError as exc:
                blocked += 1
                self.stdout.write(
                    f"BLOCKED: {job.pk} — {exc}"
                )
            else:
                ready += 1
                self.stdout.write(
                    f"VALIDATED: {job.pk} — "
                    "dry-run only; no deletion performed"
                )

        self.stdout.write(
            f"Summary: {ready} validated, "
            f"{blocked} blocked. "
            "No cleanup jobs were executed."
        )
