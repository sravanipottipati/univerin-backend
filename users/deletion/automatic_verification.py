"""
Independent, read-only verification for automatic account deletion.

This service does not delete external assets, clear database fields,
complete cleanup jobs, or erase accounts.
"""

from cloudinary import api as cloudinary_api
from django.conf import settings
from django.db import connection, transaction

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.origin_reference_guard import validate_origin_reference
from users.deletion.asset_policy import get_asset_policy
from users.deletion.cloudinary_readonly_verifier import (
    CloudinaryReadOnlyVerifier,
)
from users.deletion.reconciliation_models import (
    AutomaticDeletionVerificationAudit,
)


class AutomaticVerificationError(Exception):
    pass


def _require_authorization():
    if not getattr(
        settings, "ACCOUNT_DELETION_AUTOMATIC_ENABLED", False
    ):
        raise AutomaticVerificationError(
            "Automatic deletion is disabled."
        )

    if not getattr(
        settings,
        "ACCOUNT_DELETION_CLOUDINARY_VERIFICATION_ENABLED",
        False,
    ):
        raise AutomaticVerificationError(
            "Cloudinary verification is disabled."
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
        raise AutomaticVerificationError(
            "Automatic verification is not authorized."
        )


def verify_automatic_cleanup_asset(job_id, attempt_id):
    _require_authorization()

    # Read and validate before contacting external storage.
    job = AccountDeletionAsset.objects.select_related(
        "deletion_request",
        "deletion_request__user",
    ).get(pk=job_id)

    if (
        job.status != "processing"
        or str(job.attempt_id) != str(attempt_id)
    ):
        raise AutomaticVerificationError(
            "Cleanup attempt is not current."
        )

    if (
        job.attempts < 1
        or job.storage_deletion_confirmed_at is None
        or job.lease_expires_at is None
        or job.lease_expires_at > __import__(
            "django.utils.timezone", fromlist=["now"]
        ).now()
        or job.last_error
    ):
        raise AutomaticVerificationError(
            "Successful storage deletion has not been recorded."
        )

    validate_origin_reference(job)

    policy = get_asset_policy(
        job.owner_type,
        job.field_name,
    )

    reference = job.storage_reference
    resource_type = job.resource_type
    storage = policy["storage"]

    # External network request occurs outside transaction.atomic.
    try:
        result = CloudinaryReadOnlyVerifier(client=cloudinary_api).verify(
            reference,
            resource_type=resource_type,
            storage=storage,
        )
        state = result.state
        evidence_reference = result.evidence_reference
    except Exception:
        state = "unknown"
        evidence_reference = ""

    if state not in ("absent", "exists", "unknown"):
        state = "unknown"

    # Lock and revalidate the cleanup attempt and asset identity
    # before persisting evidence.
    with transaction.atomic():
        locked = AccountDeletionAsset.objects.select_for_update().get(
            pk=job_id
        )

        if (
            locked.status != "processing"
            or str(locked.attempt_id) != str(attempt_id)
            or locked.storage_reference != reference
            or locked.resource_type != resource_type
            or locked.owner_type != job.owner_type
            or locked.field_name != job.field_name
        ):
            raise AutomaticVerificationError(
                "Cleanup attempt or asset identity changed."
            )

        validate_origin_reference(locked)

        audit = AutomaticDeletionVerificationAudit.objects.create(
            cleanup_job=locked,
            attempt_id=locked.attempt_id,
            state=state,
            storage_reference=reference,
            resource_type=resource_type,
            storage_provider=storage,
            evidence_reference=evidence_reference or "",
        )

    return {
        "job_id": str(job_id),
        "attempt_id": str(attempt_id),
        "verification_state": state,
        "audit_id": str(audit.pk),
        "account_erased": False,
        "cleanup_finalized": False,
    }
