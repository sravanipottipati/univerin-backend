"""
Account deletion cleanup executor.

External storage deletion remains disabled by default.

Every execution attempt must revalidate the original asset
reference and ownership before invoking a storage adapter.
"""

from django.conf import settings
from django.db import connection, transaction

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.asset_policy import get_asset_policy
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.storage_adapter import (
    DisabledStorageAdapter,
    FakeStorageAdapter,
    CloudinaryStorageAdapter,
)
from users.deletion.origin_reference_guard import (
    OriginReferenceError,
    validate_origin_reference,
)


class CleanupExecutionError(Exception):
    pass


def _require_reconciliation(job_id, attempt_id, message):
    """
    Preserve processing state when ownership or storage outcome
    is uncertain. Never automatically retry an uncertain attempt.
    """
    with transaction.atomic():
        locked_job = (
            AccountDeletionAsset.objects
            .select_for_update()
            .get(pk=job_id)
        )

        if (
            locked_job.status != "processing"
            or locked_job.attempt_id != attempt_id
        ):
            raise CleanupExecutionError(
                "Cleanup attempt is stale; refusing to update job."
            )

        locked_job.last_error = (
            "Reconciliation required: " + str(message)
        )

        locked_job.save(
            update_fields=["last_error", "updated_at"]
        )

    return {
        "job_id": str(job_id),
        "status": "processing",
        "requires_reconciliation": True,
        "automatic_retry_allowed": False,
        "external_deletion_performed": False,
        "error": str(message),
    }


def execute_cleanup_job(job_id, *, adapter=None):
    """
    Execute cleanup only after revalidating the original asset.

    A successful storage response does not independently
    authorize database-reference clearing or account finalization.
    """
    if adapter is None:
        adapter = DisabledStorageAdapter()

    # Reject unauthorized adapters before claiming or modifying a job.
    if type(adapter) is DisabledStorageAdapter:
        pass

    elif type(adapter) is FakeStorageAdapter:
        if not getattr(
            settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False
        ):
            raise CleanupExecutionError(
                "Fake cleanup is restricted to isolated tests."
            )

    elif type(adapter) is CloudinaryStorageAdapter:
        if not (
            getattr(settings, "ACCOUNT_DELETION_AUTOMATIC_ENABLED", False)
            and getattr(
                settings,
                "ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED",
                False,
            )
            and not settings.DEBUG
            and getattr(
                settings, "ACCOUNT_DELETION_RAILWAY_ENVIRONMENT", ""
            ) == "production"
            and connection.settings_dict["NAME"]
                != "univerin_deletion_test_20261115"
            and connection.settings_dict["NAME"]
                != settings.DATABASES["default"].get("TEST", {}).get("NAME")
        ):
            raise CleanupExecutionError(
                "Production storage deletion is not authorized."
            )

    else:
        raise CleanupExecutionError(
            "Unapproved storage cleanup adapter."
        )

    job = claim_cleanup_job(job_id)
    attempt_id = job.attempt_id

    # Revalidate the original database reference immediately
    # before invoking the external storage adapter.
    try:
        validate_origin_reference(job)

    except Exception as exc:
        return _require_reconciliation(
            job_id,
            attempt_id,
            "Original asset ownership/reference validation failed: "
            + str(exc),
        )

    try:
        policy = get_asset_policy(
            job.owner_type,
            job.field_name,
        )

        result = adapter.delete(
            job.storage_reference,
            resource_type=job.resource_type,
            storage=policy["storage"],
            owner_type=job.owner_type,
            field_name=job.field_name,
        )

        if (
            not isinstance(result, dict)
            or result.get("result") != "ok"
        ):
            raise CleanupExecutionError(
                "Storage adapter did not confirm successful cleanup."
            )

    except Exception as exc:
        return _require_reconciliation(
            job_id,
            attempt_id,
            "Storage outcome uncertain: " + str(exc),
        )

    # Storage reported success. End the execution lease so that
    # independent, administrator-authorized verification can begin.
    # The job remains processing; no database reference is cleared.
    from django.utils import timezone

    with transaction.atomic():
        locked_job = (
            AccountDeletionAsset.objects
            .select_for_update()
            .get(pk=job_id)
        )

        if (
            locked_job.status != "processing"
            or locked_job.attempt_id != attempt_id
        ):
            raise CleanupExecutionError(
                "Cleanup attempt changed after storage execution; "
                "manual reconciliation required."
            )

        locked_job.lease_expires_at = timezone.now()
        locked_job.save(
            update_fields=["lease_expires_at", "updated_at"]
        )

    return {
        "job_id": str(job_id),
        "status": "processing",
        "storage_result": result,
        "attempt_id": str(attempt_id),
        "requires_finalization": True,
        "external_deletion_performed": True,
    }


def execute_mock_cleanup_and_finalize(job_id, *, fail=False):
    """
    Test-only end-to-end cleanup.

    Never contacts Cloudinary or production storage.
    """
    from django.conf import settings

    from users.deletion.storage_adapter import FakeStorageAdapter
    from users.deletion.cleanup_finalizer import finalize_cleanup_job

    if not getattr(
        settings,
        "TESTING_ACCOUNT_DELETION_CLEANUP",
        False,
    ):
        raise CleanupExecutionError(
            "Mock account cleanup is disabled outside test environments."
        )

    adapter = FakeStorageAdapter(fail=fail)

    result = execute_cleanup_job(job_id, adapter=adapter)

    if result.get("requires_reconciliation"):
        return result

    if not result.get("requires_finalization"):
        raise CleanupExecutionError(
            "Cleanup did not request finalization."
        )

    # Compatibility with the legacy test-only finalizer.
    # Never restore a lease outside the isolated test database.
    from datetime import timedelta
    from django.utils import timezone
    from django.db import connection

    database_name = connection.settings_dict["NAME"]
    if not (
        getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False)
        and database_name == "univerin_deletion_test_20261115"
        and settings.DATABASES["default"].get("TEST", {}).get("NAME")
            == database_name
        and type(adapter) is FakeStorageAdapter
    ):
        raise CleanupExecutionError(
            "Legacy mock finalization requires the isolated test database."
        )

    with transaction.atomic():
        locked_job = (
            AccountDeletionAsset.objects
            .select_for_update()
            .get(pk=job_id)
        )

        if (
            locked_job.status != "processing"
            or str(locked_job.attempt_id) != result["attempt_id"]
        ):
            raise CleanupExecutionError(
                "Mock cleanup attempt changed before finalization."
            )

        locked_job.lease_expires_at = (
            timezone.now() + timedelta(minutes=15)
        )
        locked_job.save(
            update_fields=["lease_expires_at", "updated_at"]
        )

    finalized_job = finalize_cleanup_job(
        job_id,
        storage_result=result["storage_result"],
        attempt_id=result["attempt_id"],
    )

    return {
        "job_id": str(finalized_job.pk),
        "status": finalized_job.status,
        "mock_only": True,
        "external_deletion_performed": False,
    }
