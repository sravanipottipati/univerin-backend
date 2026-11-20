"""
Evidence-backed automatic cleanup finalization.

Does not contact external storage, delete files, or erase accounts.
"""

import uuid

from django.db import transaction
from django.utils import timezone

from users.deletion.automatic_verification import (
    _require_authorization,
)
from users.deletion.asset_policy import get_asset_policy
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.origin_reference_guard import (
    validate_origin_reference,
)
from users.deletion.reconciliation_models import (
    AutomaticDeletionVerificationAudit,
    AccountDeletionReconciliationAudit,
)


class AutomaticFinalizationError(Exception):
    pass


@transaction.atomic
def finalize_automatic_cleanup_job(
    job_id, *, attempt_id, verification_audit_id
):
    _require_authorization()

    try:
        attempt = uuid.UUID(str(attempt_id))
        audit_id = uuid.UUID(str(verification_audit_id))
    except (TypeError, ValueError, AttributeError):
        raise AutomaticFinalizationError(
            "Invalid cleanup attempt or verification ID."
        ) from None

    job = (
        AccountDeletionAsset.objects
        .select_for_update(of=("self",))
        .select_related("deletion_request__user")
        .get(pk=job_id)
    )

    if job.status != "processing" or job.attempt_id != attempt:
        raise AutomaticFinalizationError(
            "Cleanup job or attempt is stale."
        )

    if (
        job.attempts < 1
        or job.storage_deletion_confirmed_at is None
        or job.lease_expires_at is None
        or job.lease_expires_at > timezone.now()
        or job.last_error
    ):
        raise AutomaticFinalizationError(
            "Cleanup execution is not ready for finalization."
        )

    request = job.deletion_request
    user = request.user

    if (
        user is None
        or request.status not in ("pending", "processing")
        or not user.is_active
        or user.is_deleted
        or user.is_staff
        or user.is_admin
        or request.account_type != user.user_type
    ):
        raise AutomaticFinalizationError(
            "Account is not eligible for automatic finalization."
        )

    from users.play_review_otp import is_restricted_review_account

    if is_restricted_review_account(user.phone_number):
        raise AutomaticFinalizationError(
            "Protected review account."
        )

    expected_storage = get_asset_policy(
        job.owner_type, job.field_name
    )["storage"]

    verification = AutomaticDeletionVerificationAudit.objects.filter(
        pk=audit_id,
        cleanup_job=job,
        attempt_id=attempt,
        state=AutomaticDeletionVerificationAudit.State.ABSENT,
        storage_reference=job.storage_reference,
        resource_type=job.resource_type,
        storage_provider=expected_storage,
    ).first()

    if verification is None:
        raise AutomaticFinalizationError(
            "Matching asset-absence evidence is required."
        )

    if verification.evidence_reference != "cloudinary-admin-not-found":
        raise AutomaticFinalizationError(
            "Unrecognized absence-verification evidence."
        )

    # A newer automatic observation overrides older absence evidence.
    if AutomaticDeletionVerificationAudit.objects.filter(
        cleanup_job=job,
        attempt_id=attempt,
        created_at__gt=verification.created_at,
    ).exists():
        raise AutomaticFinalizationError(
            "Newer automatic verification must be reviewed."
        )

    # Existing administrator reconciliation must not be bypassed.
    if AccountDeletionReconciliationAudit.objects.filter(
        cleanup_job=job,
        attempt_id=attempt,
        created_at__gt=verification.created_at,
    ).exists():
        raise AutomaticFinalizationError(
            "Newer reconciliation evidence exists."
        )

    validate_origin_reference(job)

    if job.owner_type == "user":
        owner = user
    elif job.owner_type == "vendor":
        owner = getattr(user, "vendor", None)
    elif job.owner_type == "delivery_partner":
        owner = getattr(user, "delivery_partner", None)
    else:
        owner = None

    if owner is None:
        raise AutomaticFinalizationError(
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
        raise AutomaticFinalizationError(
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

    return {
        "job_id": str(job.pk),
        "status": "completed",
        "verification_audit_id": str(verification.pk),
        "account_erased": False,
    }
