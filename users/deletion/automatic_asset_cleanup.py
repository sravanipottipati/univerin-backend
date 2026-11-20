"""
Preflight for automatic account deletion asset cleanup.

Validates eligibility and queues approved assets.
Does not delete external files or erase personal information.
"""

from django.conf import settings
from django.db import connection, transaction

from users.models import AccountDeletionRequest
from users.play_review_otp import is_restricted_review_account
from users.deletion.retention import assess_account_deletion
from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.erasure_plan import build_buyer_erasure_plan
from users.deletion.worker_erasure_plan import (
    build_vendor_erasure_plan,
    build_delivery_partner_erasure_plan,
)


class AutomaticAssetCleanupError(Exception):
    pass


@transaction.atomic
def prepare_automatic_asset_cleanup(deletion_request_id):
    if not getattr(
        settings, "ACCOUNT_DELETION_AUTOMATIC_ENABLED", False
    ):
        raise AutomaticAssetCleanupError(
            "Automatic deletion is disabled."
        )

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
        and database_name != settings.DATABASES["default"].get(
            "TEST", {}
        ).get("NAME")
    )

    if not (isolated_test_mode or production_authorized):
        raise AutomaticAssetCleanupError(
            "Automatic cleanup is not authorized for this database."
        )

    request = (
        AccountDeletionRequest.objects
        .select_for_update()
        .select_related("user")
        .get(pk=deletion_request_id)
    )

    if request.status != "pending":
        raise AutomaticAssetCleanupError(
            "Deletion request is not pending."
        )

    user = request.user

    if (
        user is None
        or not user.is_active
        or user.is_deleted
        or user.is_staff
        or user.is_admin
        or request.account_type != user.user_type
        or is_restricted_review_account(user.phone_number)
    ):
        raise AutomaticAssetCleanupError(
            "Account is protected or ineligible."
        )

    assessment = assess_account_deletion(user)

    if not assessment.can_proceed:
        raise AutomaticAssetCleanupError(
            "; ".join(assessment.blockers)
        )

    if user.user_type == "buyer":
        plan = build_buyer_erasure_plan(user)
    elif user.user_type == "vendor":
        plan = build_vendor_erasure_plan(user)
    elif user.user_type == "delivery_partner":
        plan = build_delivery_partner_erasure_plan(user)
    else:
        raise AutomaticAssetCleanupError(
            "Unsupported account type."
        )

    if not plan.get("eligible_for_erasure_review", False):
        raise AutomaticAssetCleanupError(
            "Historical records require additional review."
        )

    jobs = queue_account_deletion_assets(request)

    return {
        "request_id": str(request.pk),
        "eligible": True,
        "asset_jobs": [str(job.pk) for job in jobs],
        "external_deletion_performed": False,
        "account_erased": False,
    }
