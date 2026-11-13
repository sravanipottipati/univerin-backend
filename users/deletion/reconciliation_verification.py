"""
Audited, read-only storage verification for cleanup reconciliation.

No deletion, retry, or finalization is performed.
"""

import uuid

from django.db import transaction
from django.utils import timezone

from users.models import User
from users.deletion.asset_policy import get_asset_policy
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


@transaction.atomic
def verify_cleanup_asset(
    job_id,
    *,
    administrator,
    attempt_id,
    verifier=None,
):
    if administrator is None or getattr(administrator, "pk", None) is None:
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

    try:
        supplied_attempt = uuid.UUID(str(attempt_id))
    except (TypeError, ValueError, AttributeError):
        raise ReconciliationVerificationError(
            "Invalid cleanup attempt ID."
        ) from None

    try:
        job = (
            AccountDeletionAsset.objects
            .select_for_update(of=("self",))
            .get(pk=job_id)
        )
    except (AccountDeletionAsset.DoesNotExist, ValueError, TypeError):
        raise ReconciliationVerificationError(
            "Cleanup job not found."
        ) from None

    if job.status != "processing" or job.attempt_id != supplied_attempt:
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

    policy = get_asset_policy(job.owner_type, job.field_name)

    if verifier is None:
        verifier = DisabledStorageVerifier()

    # Fake verification must never be accepted in production.
    if isinstance(verifier, FakeStorageVerifier):
        from django.conf import settings

        if not getattr(
            settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False
        ):
            raise ReconciliationVerificationError(
                "Fake verification is disabled outside tests."
            )

    result = verifier.verify(
        job.storage_reference,
        resource_type=job.resource_type,
        storage=policy["storage"],
    )

    if (
        not isinstance(result, StorageVerificationResult)
        or result.state not in ("exists", "absent", "unknown")
        or result.provider != policy["storage"]
    ):
        raise ReconciliationVerificationError(
            "Invalid storage verification response."
        )

    decision_map = {
        "exists": AccountDeletionReconciliationAudit.Decision.ASSET_STILL_EXISTS,
        "absent": AccountDeletionReconciliationAudit.Decision.DELETION_CONFIRMED,
        "unknown": AccountDeletionReconciliationAudit.Decision.INCONCLUSIVE,
    }

    # A verification audit is informational. Even an absent result
    # does not authorize database finalization.
    audit = AccountDeletionReconciliationAudit.objects.create(
        cleanup_job=job,
        attempt_id=supplied_attempt,
        administrator_id=administrator.pk,
        decision=decision_map[result.state],
        evidence_reference=result.evidence_reference[:500],
        explanation=(
            f"Read-only storage verification returned: {result.state}. "
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
