"""
Fail-closed detection of interrupted account cleanup jobs.

Does not retry jobs, modify database records, or delete assets.
"""

from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset


def find_expired_cleanup_jobs(*, now=None):
    if now is None:
        now = timezone.now()

    return AccountDeletionAsset.objects.filter(
        status="processing",
        lease_expires_at__lte=now,
    ).order_by("lease_expires_at")


def inspect_expired_cleanup_jobs(*, now=None):
    jobs = find_expired_cleanup_jobs(now=now)

    return [
        {
            "job_id": str(job.pk),
            "attempt_id": str(job.attempt_id),
            "status": job.status,
            "lease_expires_at": job.lease_expires_at.isoformat(),
            "requires_reconciliation": True,
            "automatic_retry_allowed": False,
        }
        for job in jobs
    ]
