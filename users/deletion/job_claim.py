"""
Transactional claiming of account deletion cleanup jobs.

No external storage operations occur here.
"""

from django.db import transaction
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_worker import inspect_cleanup_job


class CleanupClaimError(Exception):
    pass


@transaction.atomic
def claim_cleanup_job(job_id):
    job = (
        AccountDeletionAsset.objects
        .select_for_update()
        .get(pk=job_id)
    )

    if job.status not in ("pending", "failed"):
        raise CleanupClaimError(
            "Cleanup job is not available for claiming."
        )

    # Recheck the asset while holding the database row lock.
    inspect_cleanup_job(job.pk)

    job.status = "processing"
    job.attempts += 1
    job.last_error = ""

    job.save(
        update_fields=[
            "status",
            "attempts",
            "last_error",
            "updated_at",
        ]
    )

    return job
