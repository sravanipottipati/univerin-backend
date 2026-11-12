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
