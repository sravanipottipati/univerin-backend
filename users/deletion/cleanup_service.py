"""
Account deletion asset cleanup orchestration.

Simulation only:
- No Cloudinary calls
- No file deletion
- No database asset-reference clearing
- No account deletion finalization

A successful simulation is NOT proof of external deletion.
"""

from django.db import transaction
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_worker import inspect_cleanup_job


class CleanupNotEnabledError(Exception):
    pass


def simulate_cleanup_attempt(job_id):
    """
    Validate an asset and simulate a cleanup attempt.

    This never marks a job completed because no external
    deletion has actually been verified.
    """
    inspection = inspect_cleanup_job(job_id)

    with transaction.atomic():
        job = (
            AccountDeletionAsset.objects
            .select_for_update()
            .get(pk=job_id)
        )

        if job.status not in ("pending", "failed"):
            raise CleanupNotEnabledError(
                "Job is not eligible for a simulated attempt."
            )

        job.attempts += 1
        job.status = "failed"
        job.last_error = (
            "Simulation only: external cleanup was not executed."
        )
        job.save(
            update_fields=[
                "attempts",
                "status",
                "last_error",
                "updated_at",
            ]
        )

    return {
        "job_id": str(job.pk),
        "inspection": inspection,
        "attempts": job.attempts,
        "status": job.status,
        "external_deletion_performed": False,
    }
