"""
Automatic account deletion orchestration.

External storage operations are never performed inside a
database transaction. Failed or uncertain cleanup stops deletion.
"""

from users.deletion.automatic_asset_cleanup import (
    prepare_automatic_asset_cleanup,
)
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_executor import execute_cleanup_job
from users.deletion.storage_adapter import CloudinaryStorageAdapter
from users.deletion.automatic_verification import (
    verify_automatic_cleanup_asset,
)
from users.deletion.automatic_finalizer import (
    finalize_automatic_cleanup_job,
)
from users.deletion.processor import (
    process_automatic_deletion_request,
)


class AutomaticOrchestrationError(Exception):
    pass


def process_automatic_deletion_with_assets(request_id):
    preparation = prepare_automatic_asset_cleanup(request_id)

    jobs = AccountDeletionAsset.objects.filter(
        deletion_request_id=request_id
    ).order_by("created_at")

    for job in jobs:
        if job.status == "completed":
            continue

        # Never retry processing/failed/uncertain jobs automatically.
        if job.status != "pending":
            raise AutomaticOrchestrationError(
                "Cleanup job requires reconciliation."
            )

        execution = execute_cleanup_job(
            job.pk,
            adapter=CloudinaryStorageAdapter(),
        )

        if (
            execution.get("requires_reconciliation")
            or not execution.get("external_deletion_performed")
            or not execution.get("requires_finalization")
        ):
            raise AutomaticOrchestrationError(
                "Storage deletion was not safely confirmed."
            )

        verification = verify_automatic_cleanup_asset(
            job.pk,
            execution["attempt_id"],
        )

        if verification["verification_state"] != "absent":
            raise AutomaticOrchestrationError(
                "Cloudinary did not independently confirm absence."
            )

        finalize_automatic_cleanup_job(
            job.pk,
            attempt_id=execution["attempt_id"],
            verification_audit_id=verification["audit_id"],
        )

    return process_automatic_deletion_request(request_id)
