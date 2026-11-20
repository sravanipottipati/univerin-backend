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

from users.models import AccountDeletionRequest, User
from users.play_review_otp import is_restricted_review_account
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

    # Authorization must use current database state, not a
    # potentially stale administrator object.
    administrator_id = getattr(approved_by, "pk", None)

    if (
        administrator_id is None
        or not getattr(approved_by, "is_authenticated", False)
        or not User.objects.filter(
            pk=administrator_id,
            is_active=True,
            is_staff=True,
            is_admin=True,
            is_deleted=False,
        ).exists()
    ):
        raise PermissionError(
            "Only an active administrator can authorize account deletion."
        )

    return _process_locked_deletion_request(request_id)


@transaction.atomic
def process_automatic_deletion_request(request_id):
    """
    Internal worker entry point.

    Not exposed through an HTTP endpoint. The management command
    must separately enforce its execution controls.
    """
    from django.conf import settings

    if not settings.ACCOUNT_DELETION_AUTOMATIC_ENABLED:
        raise PermissionError("Automatic account deletion is disabled.")

    # Check execution authorization independently of the management command.
    from django.db import connection

    database_name = connection.settings_dict["NAME"]

    isolated_test_mode = (
        getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False)
        and database_name == "univerin_deletion_test_20261115"
        and settings.DATABASES["default"].get("TEST", {}).get("NAME")
            == database_name
    )

    production_authorized = (
        not settings.DEBUG
        and getattr(
            settings,
            "ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED",
            False,
        )
        and getattr(
            settings,
            "ACCOUNT_DELETION_RAILWAY_ENVIRONMENT",
            "",
        ) == "production"
        and database_name != "univerin_deletion_test_20261115"
        and settings.DATABASES["default"].get("TEST", {}).get("NAME")
            != database_name
    )

    if not (isolated_test_mode or production_authorized):
        raise PermissionError(
            "Automatic deletion execution is not authorized."
        )

    return _process_locked_deletion_request(
        request_id,
        automatic=True,
    )


def _process_locked_deletion_request(request_id, *, automatic=False):
    """Shared transaction-locked erasure implementation."""
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

    if is_restricted_review_account(user.phone_number):
        raise ValueError(
            "Restricted reviewer accounts cannot be deleted."
        )

    if user.is_deleted:
        raise ValueError(
            "Account has already been deleted."
        )

    if not user.is_active:
        raise ValueError("Inactive accounts require review.")

    if deletion_request.account_type != user.user_type:
        raise ValueError("Deletion request account type mismatch.")

    if automatic:
        if deletion_request.status != "pending":
            raise ValueError(
                "Automatic processing requires a pending request."
            )

        if deletion_request.asset_cleanup_jobs.exclude(
            status="completed"
        ).exists():
            raise DeletionBlockedError(
                "Unresolved asset cleanup jobs require review."
            )

        from users.deletion.preview import preview_account_deletion
        from users.deletion.worker_erasure_plan import (
            build_vendor_erasure_plan,
            build_delivery_partner_erasure_plan,
        )

        preview = preview_account_deletion(user)
        if not preview["can_proceed"]:
            raise DeletionBlockedError("; ".join(preview["blockers"]))

        if user.user_type == "buyer":
            plan = build_buyer_erasure_plan(user)
            has_assets = bool(user.profile_photo)
        elif user.user_type == "vendor":
            plan = build_vendor_erasure_plan(user)
            vendor = user.vendor
            has_assets = bool(
                user.profile_photo
                or vendor.fssai_certificate
                or vendor.banner_image
            )
        elif user.user_type == "delivery_partner":
            plan = build_delivery_partner_erasure_plan(user)
            partner = user.delivery_partner
            has_assets = bool(
                user.profile_photo
                or partner.aadhaar_document
                or partner.pan_document
                or partner.driving_licence_document
                or partner.selfie_photo
            )
        else:
            raise DeletionBlockedError("Unsupported account type.")

        if not plan.get("eligible_for_erasure_review", False) or has_assets:
            raise DeletionBlockedError(
                "Historical records or uploaded assets require review."
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
