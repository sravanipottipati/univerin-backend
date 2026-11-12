"""
Transactional database finalization for asset cleanup.

Only call after a trusted storage adapter has confirmed deletion.
Production integration is not enabled.
"""

import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.asset_policy import get_asset_policy


class CleanupFinalizationError(Exception):
    pass


@transaction.atomic
def finalize_cleanup_job(job_id, *, storage_result, attempt_id=None):
    # This legacy finalizer accepts caller-supplied confirmation.
    # Keep it available only for isolated tests until replaced
    # by a verified, attempt-bound production finalizer.
    if not getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False):
        raise CleanupFinalizationError(
            "Legacy cleanup finalization is disabled."
        )

    if not isinstance(storage_result, dict):
        raise CleanupFinalizationError(
            "Missing storage deletion confirmation."
        )

    if storage_result.get("result") != "ok":
        raise CleanupFinalizationError(
            "Storage deletion was not confirmed."
        )

    job = (
        AccountDeletionAsset.objects
        .select_for_update(of=("self",))
        .select_related("deletion_request__user")
        .get(pk=job_id)
    )

    if job.status != "processing":
        raise CleanupFinalizationError(
            "Job must be processing before finalization."
        )

    # A successful storage result alone does not authorize finalization.
    try:
        supplied_attempt_id = uuid.UUID(str(attempt_id))
    except (ValueError, TypeError, AttributeError):
        supplied_attempt_id = None

    if (
        supplied_attempt_id is None
        or job.attempt_id != supplied_attempt_id
    ):
        raise CleanupFinalizationError(
            "Cleanup attempt identity is missing or stale."
        )

    if (
        job.lease_expires_at is None
        or job.lease_expires_at <= timezone.now()
    ):
        raise CleanupFinalizationError(
            "Cleanup worker lease has expired."
        )

    request = job.deletion_request
    user = request.user

    if user is None or request.status not in ("pending", "processing"):
        raise CleanupFinalizationError(
            "Deletion request is not eligible."
        )

    get_asset_policy(job.owner_type, job.field_name)

    if job.owner_type == "user":
        owner = user
    elif job.owner_type == "vendor":
        owner = getattr(user, "vendor", None)
    elif job.owner_type == "delivery_partner":
        owner = getattr(user, "delivery_partner", None)
    else:
        owner = None

    if owner is None:
        raise CleanupFinalizationError(
            "Asset owner could not be verified."
        )

    owner = type(owner).objects.select_for_update().get(pk=owner.pk)

    field = getattr(owner, job.field_name)
    current_reference = (
        getattr(field, "public_id", None)
        or getattr(field, "name", None)
        or str(field)
    )

    if current_reference != job.storage_reference:
        raise CleanupFinalizationError(
            "Asset reference changed before finalization."
        )

    setattr(owner, job.field_name, None)
    owner.save(update_fields=[job.field_name])

    job.status = "completed"
    job.lease_expires_at = None
    job.completed_at = timezone.now()
    job.last_error = ""
    job.save(
        update_fields=[
            "status",
            "lease_expires_at",
            "completed_at",
            "last_error",
            "updated_at",
        ]
    )

    return job
