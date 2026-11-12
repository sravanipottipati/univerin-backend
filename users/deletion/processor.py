"""
Account deletion processor.

- Requires administrator authorization.
- Locks deletion requests and associated users.
- Reassesses outstanding obligations.
- Performs supported account anonymization.
- Marks requests completed only after successful database erasure.
- Blocks accounts requiring external asset cleanup.
"""

from django.db import transaction
from django.utils import timezone

from users.models import AccountDeletionRequest
from users.deletion.retention import assess_account_deletion
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.erasure_plan import build_buyer_erasure_plan
from users.deletion.buyer_erasure import erase_buyer_personal_data
from users.deletion.worker_erasure import (
    erase_vendor_personal_data,
    erase_delivery_partner_personal_data,
)


class DeletionBlockedError(Exception):
    """Account deletion cannot proceed due to outstanding obligations."""


class DeletionNotImplementedError(Exception):
    """Personal-data erasure has not yet been implemented."""


@transaction.atomic
def process_deletion_request(request_id, *, approved_by=None):
    """
    Process an administrator-approved account deletion request.

    External asset cleanup is not implemented here.
    Accounts with protected uploaded assets must remain pending.
    """

    if (
        approved_by is None
        or not getattr(approved_by, "is_authenticated", False)
        or not getattr(approved_by, "is_active", False)
        or not getattr(approved_by, "is_staff", False)
        or not getattr(approved_by, "is_admin", False)
    ):
        raise PermissionError(
            "Only an active administrator can authorize account deletion."
        )

    deletion_request = (
        AccountDeletionRequest.objects
        .select_for_update(of=("self",))
        .select_related("user")
        .get(pk=request_id)
    )

    if deletion_request.status not in ("pending", "processing"):
        raise ValueError(
            "Only pending or processing requests can be processed."
        )

    user = deletion_request.user

    if user is not None:
        user = (
            type(user).objects
            .select_for_update()
            .get(pk=user.pk)
        )

    if user is None:
        raise ValueError(
            "Deletion request has no associated user."
        )

    if user.is_staff or user.is_admin:
        raise ValueError(
            "Administrator accounts cannot use self-service deletion."
        )

    if user.is_deleted:
        raise ValueError(
            "Account has already been deleted."
        )

    assessment = assess_account_deletion(user)

    if not assessment.can_proceed:
        raise DeletionBlockedError(
            "; ".join(assessment.blockers)
        )

    # Inventory external assets before any personal-data erasure.
    # Queue creation is database-transactional; no Cloudinary
    # deletion is performed here.
    cleanup_jobs = queue_account_deletion_assets(deletion_request)

    # Previously queued cleanup jobs must all be completed.
    # Completed jobs may no longer appear in the current asset
    # inventory because their model fields have been cleared.
    all_cleanup_jobs = deletion_request.asset_cleanup_jobs.all()

    if all_cleanup_jobs.exclude(status="completed").exists():
        return deletion_request

    if cleanup_jobs:
        # Newly discovered assets still require cleanup.
        return deletion_request

    if user.user_type == "buyer":
        plan = build_buyer_erasure_plan(user)

        if not plan.get("eligible_for_erasure_review", False):
            raise DeletionNotImplementedError(
                "Buyer requires additional retention review."
            )

        # External Cloudinary cleanup requires a separate,
        # retryable workflow before photo-bearing accounts
        # can be processed.
        if user.profile_photo and user.profile_photo.name:
            raise DeletionNotImplementedError(
                "Profile photo cleanup is not yet transaction-safe."
            )

        erase_buyer_personal_data(user)

        deletion_request.status = "completed"
        deletion_request.completed_at = timezone.now()
        deletion_request.failure_reason = ""
        deletion_request.save(
            update_fields=[
                "status",
                "completed_at",
                "failure_reason",
                "updated_at",
            ]
        )

        return deletion_request

    if user.user_type == "vendor":
        erase_vendor_personal_data(user)

    elif user.user_type == "delivery_partner":
        erase_delivery_partner_personal_data(user)

    else:
        raise DeletionNotImplementedError(
            "Unsupported account type."
        )

    deletion_request.status = "completed"
    deletion_request.completed_at = timezone.now()
    deletion_request.failure_reason = ""
    deletion_request.save(
        update_fields=[
            "status",
            "completed_at",
            "failure_reason",
            "updated_at",
        ]
    )

    return deletion_request
