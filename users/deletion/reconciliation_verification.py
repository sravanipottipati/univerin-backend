"""
Read-only, audited storage verification.

Provider calls occur outside database transactions.
No deletion, retry, or finalization is performed.
"""

import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.models import User
from users.deletion.asset_policy import get_asset_policy
from users.deletion.origin_reference_guard import (
    OriginReferenceError,
    validate_origin_reference,
)
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)
from users.deletion.storage_verification import (
    DisabledStorageVerifier,
    FakeStorageVerifier,
    StorageVerificationResult,
)


class ReconciliationVerificationError(Exception):
    pass


def _authorize(administrator):
    if (
        administrator is None
        or not getattr(administrator, "is_authenticated", False)
        or getattr(administrator, "pk", None) is None
    ):
        raise ReconciliationVerificationError(
            "Administrator authorization required."
        )

    if not User.objects.filter(
        pk=administrator.pk,
        is_active=True,
        is_staff=True,
        is_admin=True,
    ).exists():
        raise ReconciliationVerificationError(
            "Administrator authorization required."
        )

    if not AccountDeletionReconciliationAccess.objects.filter(
        administrator_id=administrator.pk,
        is_enabled=True,
    ).exists():
        raise ReconciliationVerificationError(
            "Explicit reconciliation authorization required."
        )


def _validate_job(job, supplied_attempt):
    if (
        job.status != "processing"
        or job.attempt_id != supplied_attempt
    ):
        raise ReconciliationVerificationError(
            "Cleanup job or attempt is not eligible."
        )

    if not (
        job.last_error
        or job.lease_expires_at is None
        or job.lease_expires_at <= timezone.now()
    ):
        raise ReconciliationVerificationError(
            "Cleanup job does not require reconciliation."
        )


def verify_cleanup_asset(
    job_id,
    *,
    administrator,
    attempt_id,
    verifier=None,
):
    try:
        supplied_attempt = uuid.UUID(str(attempt_id))
    except (TypeError, ValueError, AttributeError):
        raise ReconciliationVerificationError(
            "Invalid cleanup attempt ID."
        ) from None

    # Only the built-in fake verifier is permitted in test mode.
    # Production verification remains disabled.
    if verifier is None:
        verifier = DisabledStorageVerifier()
    elif (
        not getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False)
        or type(verifier) is not FakeStorageVerifier
    ):
        raise ReconciliationVerificationError(
            "Injected storage verification is disabled."
        )

    # Transaction A: capture expected state.
    with transaction.atomic():
        _authorize(administrator)

        try:
            job = (
                AccountDeletionAsset.objects
                .select_for_update(of=("self",))
                .get(pk=job_id)
            )
        except (
            AccountDeletionAsset.DoesNotExist,
            ValueError,
            TypeError,
        ):
            raise ReconciliationVerificationError(
                "Cleanup job not found."
            ) from None

        _validate_job(job, supplied_attempt)

        try:
            validate_origin_reference(job)
        except OriginReferenceError as exc:
            raise ReconciliationVerificationError(str(exc)) from exc

        policy = get_asset_policy(
            job.owner_type,
            job.field_name,
        )

        expected_reference = job.storage_reference
        expected_resource_type = job.resource_type
        expected_storage = policy["storage"]
        expected_owner_type = job.owner_type
        expected_field_name = job.field_name
        expected_request_id = job.deletion_request_id

    # Outside transaction: no row lock is held.
    result = verifier.verify(
        expected_reference,
        resource_type=expected_resource_type,
        storage=expected_storage,
    )

    if (
        not isinstance(result, StorageVerificationResult)
        or result.state not in ("exists", "absent", "unknown")
        or result.provider != expected_storage
    ):
        raise ReconciliationVerificationError(
            "Invalid storage verification response."
        )

    decision_map = {
        "exists": (
            AccountDeletionReconciliationAudit.Decision.ASSET_STILL_EXISTS
        ),
        "absent": (
            AccountDeletionReconciliationAudit.Decision.ASSET_ABSENT_OBSERVED
        ),
        "unknown": (
            AccountDeletionReconciliationAudit.Decision.INCONCLUSIVE
        ),
    }

    # Transaction B: reject stale observations.
    with transaction.atomic():
        _authorize(administrator)

        job = (
            AccountDeletionAsset.objects
            .select_for_update(of=("self",))
            .get(pk=job_id)
        )

        _validate_job(job, supplied_attempt)

        try:
            validate_origin_reference(job)
        except OriginReferenceError as exc:
            raise ReconciliationVerificationError(str(exc)) from exc

        if (
            job.storage_reference != expected_reference
            or job.resource_type != expected_resource_type
            or job.owner_type != expected_owner_type
            or job.field_name != expected_field_name
            or job.deletion_request_id != expected_request_id
        ):
            raise ReconciliationVerificationError(
                "Cleanup job changed during verification."
            )

        audit = AccountDeletionReconciliationAudit.objects.create(
            cleanup_job=job,
            attempt_id=supplied_attempt,
            administrator_id=administrator.pk,
            decision=decision_map[result.state],
            evidence_reference=result.evidence_reference[:500],
            explanation=(
                "Read-only storage observation: "
                f"{result.state}. "
                "No cleanup finalization was performed."
            ),
        )

    return {
        "job_id": str(job.pk),
        "attempt_id": str(supplied_attempt),
        "verification_state": result.state,
        "audit_id": str(audit.pk),
        "finalization_allowed": False,
        "automatic_retry_allowed": False,
    }
