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
    from django.db import connection

    database_name = connection.settings_dict["NAME"]
    isolated_test_mode = (
        getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False)
        and database_name == "univerin_deletion_test_20261115"
        and settings.DATABASES["default"].get("TEST", {}).get("NAME")
            == database_name
    )

    if not isolated_test_mode:
        raise CleanupFinalizationError(
            "Legacy cleanup finalization is restricted to "
            "the isolated test database."
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


@transaction.atomic
def finalize_verified_cleanup_job(
    job_id, *, administrator, attempt_id, confirmation_audit_id
):
    """
    Finalize a reconciled cleanup job after explicit confirmation.

    Does not contact Cloudinary or perform external deletion.
    """
    from users.deletion.reconciliation_models import (
        AccountDeletionReconciliationAudit,
    )
    from users.deletion.reconciliation_verification import _authorize
    from users.deletion.origin_reference_guard import (
        validate_origin_reference,
        OriginReferenceError,
    )

    try:
        supplied_attempt = uuid.UUID(str(attempt_id))
        supplied_audit = uuid.UUID(str(confirmation_audit_id))
    except (TypeError, ValueError, AttributeError):
        raise CleanupFinalizationError(
            "Invalid attempt or confirmation ID."
        ) from None

    # Recheck administrator privileges against the database.
    _authorize(administrator)

    job = (
        AccountDeletionAsset.objects
        .select_for_update(of=("self",))
        .select_related("deletion_request__user")
        .get(pk=job_id)
    )

    if job.status != "processing" or job.attempt_id != supplied_attempt:
        raise CleanupFinalizationError(
            "Cleanup job or attempt is stale."
        )

    request = job.deletion_request
    user = request.user

    if user is None or request.status not in ("pending", "processing"):
        raise CleanupFinalizationError(
            "Deletion request is not eligible."
        )

    audit = AccountDeletionReconciliationAudit.objects.filter(
        pk=supplied_audit,
        cleanup_job=job,
        attempt_id=supplied_attempt,
        administrator_id=administrator.pk,
        decision=(
            AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED
        ),
    ).first()

    if audit is None:
        raise CleanupFinalizationError(
            "Explicit deletion confirmation is required."
        )

    # Confirmation must reference a specific absence-verification audit.
    try:
        verification_id = uuid.UUID(str(audit.evidence_reference))
    except (TypeError, ValueError, AttributeError):
        raise CleanupFinalizationError(
            "Confirmation has no valid verification reference."
        ) from None

    verification = AccountDeletionReconciliationAudit.objects.filter(
        pk=verification_id,
        cleanup_job=job,
        attempt_id=supplied_attempt,
        decision=(
            AccountDeletionReconciliationAudit.Decision
            .ASSET_ABSENT_OBSERVED
        ),
        created_at__lte=audit.created_at,
    ).first()

    if verification is None:
        raise CleanupFinalizationError(
            "Confirmation lacks matching asset-absence evidence."
        )

    # Independently validate the exact verified asset identity.
    expected_storage = get_asset_policy(
        job.owner_type,
        job.field_name,
    )["storage"]

    if (
        not verification.verified_storage_reference
        or verification.verified_storage_reference != job.storage_reference
        or verification.verified_resource_type != job.resource_type
        or verification.verified_storage_provider != expected_storage
    ):
        raise CleanupFinalizationError(
            "Verification evidence does not match the cleanup asset."
        )

    # Reject evidence superseded by a later storage observation.
    if AccountDeletionReconciliationAudit.objects.filter(
        cleanup_job=job,
        attempt_id=supplied_attempt,
        decision__in=[
            AccountDeletionReconciliationAudit.Decision.ASSET_ABSENT_OBSERVED,
            AccountDeletionReconciliationAudit.Decision.ASSET_STILL_EXISTS,
            AccountDeletionReconciliationAudit.Decision.INCONCLUSIVE,
        ],
        created_at__gt=verification.created_at,
    ).exists():
        raise CleanupFinalizationError(
            "Newer verification evidence requires administrator review."
        )

    # Validate current ownership and ensure the reference is not shared.
    try:
        validate_origin_reference(job)
    except OriginReferenceError as exc:
        raise CleanupFinalizationError(str(exc)) from exc

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

    job.save(update_fields=[
        "status",
        "lease_expires_at",
        "completed_at",
        "last_error",
        "updated_at",
    ])

    return job
