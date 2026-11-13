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
