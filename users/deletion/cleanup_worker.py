"""
Safety checks for account deletion asset cleanup.

Dry-run only. Does not contact Cloudinary or delete files.
"""

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.asset_policy import get_asset_policy
from users.deletion.cloudinary_cleanup import (
    build_cloudinary_cleanup_plan,
)
from users.deletion.cloudinary_safety import (
    validate_cloudinary_reference,
)


class AssetCleanupBlockedError(Exception):
    """Asset cleanup cannot proceed safely."""


def inspect_cleanup_job(job_id):
    job = (
        AccountDeletionAsset.objects
        .select_related("deletion_request__user")
        .get(pk=job_id)
    )

    deletion_request = job.deletion_request
    user = deletion_request.user

    if user is None:
        raise AssetCleanupBlockedError(
            "Deletion request has no associated user."
        )

    if deletion_request.status not in ("pending", "processing"):
        raise AssetCleanupBlockedError(
            "Deletion request is not awaiting cleanup."
        )

    if deletion_request.account_type != user.user_type:
        raise AssetCleanupBlockedError(
            "Account type mismatch."
        )

    if job.status == "completed":
        raise AssetCleanupBlockedError(
            "Cleanup job is already completed."
        )

    try:
        policy = get_asset_policy(
            job.owner_type,
            job.field_name,
        )
    except ValueError as exc:
        raise AssetCleanupBlockedError(
            "Asset field is not approved for cleanup."
        ) from exc

    if job.resource_type != policy["resource_type"]:
        raise AssetCleanupBlockedError(
            "Cloudinary resource type mismatch."
        )

    if not validate_cloudinary_reference(
        job.storage_reference
    ):
        raise AssetCleanupBlockedError(
            "Invalid stored asset reference."
        )

    plan = build_cloudinary_cleanup_plan(user)

    matching_assets = [
        asset
        for asset in plan["assets"]
        if asset["owner"] == job.owner_type
        and asset["field"] == job.field_name
    ]

    if len(matching_assets) != 1:
        raise AssetCleanupBlockedError(
            "Asset is no longer present on its original field."
        )

    current_reference = matching_assets[0][
        "storage_reference"
    ]

    if current_reference != job.storage_reference:
        raise AssetCleanupBlockedError(
            "Asset reference changed after queue creation."
        )

    return {
        "job_id": str(job.pk),
        "owner_type": job.owner_type,
        "field_name": job.field_name,
        "reference_verified": True,
        "ready_for_external_cleanup": False,
        "reason": (
            "Dry-run verification passed. "
            "External cleanup is not enabled."
        ),
    }
