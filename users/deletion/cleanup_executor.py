"""
Mocked account deletion cleanup executor.

External storage deletion is disabled by default.
This module does not clear model fields or finalize accounts.
"""

from django.db import transaction
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.asset_policy import get_asset_policy
from users.deletion.job_claim import claim_cleanup_job
from users.deletion.storage_adapter import DisabledStorageAdapter


class CleanupExecutionError(Exception):
    pass


def execute_cleanup_job(job_id, *, adapter=None):
    """
    Execute a cleanup attempt using an injected storage adapter.

    A successful adapter response is not sufficient to finalize
    account deletion. Database references remain unchanged.
    """
    if adapter is None:
        adapter = DisabledStorageAdapter()

    job = claim_cleanup_job(job_id)

    policy = get_asset_policy(job.owner_type, job.field_name)

    try:
        result = adapter.delete(
            job.storage_reference,
            resource_type=job.resource_type,
            storage=policy["storage"],
        )

        if not isinstance(result, dict) or result.get("result") != "ok":
            raise CleanupExecutionError(
                "Storage adapter did not confirm successful cleanup."
            )

    except Exception as exc:
        with transaction.atomic():
            locked_job = (
                AccountDeletionAsset.objects
                .select_for_update()
                .get(pk=job_id)
            )

            locked_job.status = "failed"
            locked_job.last_error = str(exc)
            locked_job.save(
                update_fields=[
                    "status",
                    "last_error",
                    "updated_at",
                ]
            )

        return {
            "job_id": str(job_id),
            "status": "failed",
            "error": str(exc),
        }

    # Do not mark the job completed yet: the database field still
    # references the asset, and finalization has not been implemented.
    return {
        "job_id": str(job_id),
        "status": "processing",
        "storage_result": result,
        "requires_finalization": True,
    }


def execute_mock_cleanup_and_finalize(job_id, *, fail=False):
    """
    Test-only end-to-end cleanup.

    Never contacts Cloudinary or other external storage.
    Must not be used as evidence of real storage deletion.
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

    if result["status"] != "processing":
        return result

    if not result.get("requires_finalization"):
        raise CleanupExecutionError(
            "Cleanup did not request finalization."
        )

    finalized_job = finalize_cleanup_job(
        job_id,
        storage_result=result["storage_result"],
    )

    return {
        "job_id": str(finalized_job.pk),
        "status": finalized_job.status,
        "mock_only": True,
        "external_deletion_performed": False,
    }
