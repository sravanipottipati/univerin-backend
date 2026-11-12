"""
Read-only inspection for account deletion cleanup reconciliation.

Does not modify records, retry cleanup, or delete storage assets.
"""

from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset


class CleanupReconciliationError(Exception):
    pass


def inspect_cleanup_for_reconciliation(job_id, *, admin):
    """
    Return a minimal operational summary of a cleanup job.

    Requires an active staff administrator.
    Does not expose the storage reference.
    """
    if (
        admin is None
        or not getattr(admin, "is_authenticated", False)
        or not getattr(admin, "is_active", False)
        or not getattr(admin, "is_staff", False)
    ):
        raise CleanupReconciliationError(
            "Administrator authorization required."
        )

    try:
        job = AccountDeletionAsset.objects.get(pk=job_id)
    except (AccountDeletionAsset.DoesNotExist, ValueError, TypeError):
        raise CleanupReconciliationError(
            "Cleanup job not found."
        ) from None

    now = timezone.now()

    lease_expired = (
        job.lease_expires_at is not None
        and job.lease_expires_at <= now
    )

    outcome_uncertain = (
        job.status == "processing"
        and bool(job.last_error)
    )

    requires_reconciliation = (
        job.status == "processing"
        and (
            lease_expired
            or outcome_uncertain
            or job.lease_expires_at is None
        )
    )

    return {
        "job_id": str(job.pk),
        "deletion_request_id": str(job.deletion_request_id),
        "owner_type": job.owner_type,
        "field_name": job.field_name,
        "status": job.status,
        "attempt_id": (
            str(job.attempt_id)
            if job.attempt_id else None
        ),
        "attempts": job.attempts,
        "lease_expired": lease_expired,
        "outcome_uncertain": outcome_uncertain,
        "requires_reconciliation": requires_reconciliation,
        "automatic_retry_allowed": False,
        "storage_reference_exposed": False,
    }
