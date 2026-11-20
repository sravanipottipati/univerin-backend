"""
Audited account deletion reconciliation decisions.

This service records investigations only.
It does not retry cleanup, finalize jobs, or delete assets.
"""

import uuid

from django.db import transaction

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)


class ReconciliationDecisionError(Exception):
    pass


@transaction.atomic
def begin_cleanup_investigation(
    job_id,
    *,
    administrator,
    attempt_id,
    explanation,
):
    """
    Record an authorized investigation for an uncertain cleanup job.
    """

    if (
        administrator is None
        or not getattr(administrator, "is_authenticated", False)
        or not getattr(administrator, "is_active", False)
        or not getattr(administrator, "is_staff", False)
        or not getattr(administrator, "is_admin", False)
        or getattr(administrator, "pk", None) is None
    ):
        raise ReconciliationDecisionError(
            "Administrator authorization required."
        )

    # Re-read authorization from the database rather than trusting
    # potentially stale administrator attributes.
    from users.models import User

    authorized = User.objects.filter(
        pk=administrator.pk,
        is_active=True,
        is_staff=True,
        is_admin=True,
    ).exists()

    if not authorized:
        raise ReconciliationDecisionError(
            "Administrator authorization required."
        )

    if not AccountDeletionReconciliationAccess.objects.filter(
        administrator_id=administrator.pk,
        is_enabled=True,
    ).exists():
        raise ReconciliationDecisionError(
            "Explicit reconciliation authorization required."
        )

    if not isinstance(explanation, str):
        raise ReconciliationDecisionError(
            "A valid investigation explanation is required."
        )

    explanation = explanation.strip()

    if not 10 <= len(explanation) <= 2000:
        raise ReconciliationDecisionError(
            "Explanation must contain 10 to 2000 characters."
        )

    try:
        supplied_attempt = uuid.UUID(str(attempt_id))
    except (TypeError, ValueError, AttributeError):
        raise ReconciliationDecisionError(
            "Invalid cleanup attempt ID."
        ) from None

    try:
        job = (
            AccountDeletionAsset.objects
            .select_for_update(of=("self",))
            .get(pk=job_id)
        )
    except (AccountDeletionAsset.DoesNotExist, ValueError, TypeError):
        raise ReconciliationDecisionError(
            "Cleanup job not found."
        ) from None

    if job.status != "processing":
        raise ReconciliationDecisionError(
            "Only processing jobs may be investigated."
        )

    if job.attempt_id != supplied_attempt:
        raise ReconciliationDecisionError(
            "Cleanup attempt ID does not match."
        )

    from django.utils import timezone

    needs_reconciliation = (
        bool(job.last_error)
        or job.lease_expires_at is None
        or job.lease_expires_at <= timezone.now()
    )

    if not needs_reconciliation:
        raise ReconciliationDecisionError(
            "Cleanup job does not require reconciliation."
        )

    audit = AccountDeletionReconciliationAudit.objects.create(
        cleanup_job=job,
        attempt_id=supplied_attempt,
        administrator_id=administrator.pk,
        decision=(
            AccountDeletionReconciliationAudit.Decision.INVESTIGATING
        ),
        explanation=explanation,
        evidence_reference="",
    )

    return audit


@transaction.atomic
def confirm_cleanup_deletion(
    job_id,
    *,
    administrator,
    attempt_id,
    verification_audit_id,
    explanation,
):
    """
    Record evidence-backed administrator confirmation.

    Does not delete storage assets or finalize cleanup jobs.
    """
    from django.utils import timezone
    from users.models import User
    from users.deletion.origin_reference_guard import (
        OriginReferenceError,
        validate_origin_reference,
    )

    if (
        administrator is None
        or not getattr(administrator, "is_authenticated", False)
        or getattr(administrator, "pk", None) is None
        or not User.objects.filter(
            pk=administrator.pk,
            is_active=True,
            is_staff=True,
            is_admin=True,
        ).exists()
    ):
        raise ReconciliationDecisionError(
            "Administrator authorization required."
        )

    if not AccountDeletionReconciliationAccess.objects.filter(
        administrator_id=administrator.pk,
        is_enabled=True,
    ).exists():
        raise ReconciliationDecisionError(
            "Explicit reconciliation authorization required."
        )

    if not isinstance(explanation, str) or not (
        10 <= len(explanation.strip()) <= 2000
    ):
        raise ReconciliationDecisionError(
            "Confirmation explanation must contain 10 to 2000 characters."
        )

    try:
        supplied_attempt = uuid.UUID(str(attempt_id))
        verification_id = uuid.UUID(str(verification_audit_id))
    except (TypeError, ValueError, AttributeError):
        raise ReconciliationDecisionError(
            "Invalid attempt or verification audit ID."
        ) from None

    try:
        job = (
            AccountDeletionAsset.objects
            .select_for_update(of=("self",))
            .select_related("deletion_request__user")
            .get(pk=job_id)
        )
    except (AccountDeletionAsset.DoesNotExist, TypeError, ValueError):
        raise ReconciliationDecisionError(
            "Cleanup job not found."
        ) from None

    if job.status != "processing" or job.attempt_id != supplied_attempt:
        raise ReconciliationDecisionError(
            "Cleanup job or attempt is stale."
        )

    if job.deletion_request.status not in ("pending", "processing"):
        raise ReconciliationDecisionError(
            "Deletion request is not eligible."
        )

    if not (
        job.last_error
        or job.lease_expires_at is None
        or job.lease_expires_at <= timezone.now()
    ):
        raise ReconciliationDecisionError(
            "Cleanup job does not require reconciliation."
        )

    try:
        validate_origin_reference(job)
    except OriginReferenceError as exc:
        raise ReconciliationDecisionError(str(exc)) from exc

    verification = AccountDeletionReconciliationAudit.objects.filter(
        pk=verification_id,
        cleanup_job=job,
        attempt_id=supplied_attempt,
        decision=(
            AccountDeletionReconciliationAudit.Decision
            .ASSET_ABSENT_OBSERVED
        ),
    ).first()

    if verification is None:
        raise ReconciliationDecisionError(
            "Matching asset-absence verification is required."
        )

    # Evidence must identify the exact asset verified.
    from users.deletion.asset_policy import get_asset_policy

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
        raise ReconciliationDecisionError(
            "Verification evidence does not match the cleanup asset."
        )

    # Reject a verification superseded by a newer provider observation.
    newer_observation = (
        AccountDeletionReconciliationAudit.objects.filter(
            cleanup_job=job,
            attempt_id=supplied_attempt,
            decision__in=[
                AccountDeletionReconciliationAudit.Decision
                .ASSET_ABSENT_OBSERVED,
                AccountDeletionReconciliationAudit.Decision
                .ASSET_STILL_EXISTS,
                AccountDeletionReconciliationAudit.Decision
                .INCONCLUSIVE,
            ],
        )
        .filter(
            __import__("django.db.models", fromlist=["Q"]).Q(
                created_at__gt=verification.created_at
            )
            | (
                __import__("django.db.models", fromlist=["Q"]).Q(
                    created_at=verification.created_at,
                    pk__gt=verification.pk,
                )
            )
        )
        .exists()
    )

    if newer_observation:
        raise ReconciliationDecisionError(
            "A newer verification exists. Review the latest evidence."
        )

    if AccountDeletionReconciliationAudit.objects.filter(
        cleanup_job=job,
        attempt_id=supplied_attempt,
        decision=(
            AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED
        ),
    ).exists():
        raise ReconciliationDecisionError(
            "This cleanup attempt is already confirmed."
        )

    return AccountDeletionReconciliationAudit.objects.create(
        cleanup_job=job,
        attempt_id=supplied_attempt,
        administrator_id=administrator.pk,
        decision=(
            AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED
        ),
        evidence_reference=str(verification.pk),
        explanation=explanation.strip(),
    )
