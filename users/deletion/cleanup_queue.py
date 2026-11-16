"""
Create persistent asset cleanup jobs.

This module does not call Cloudinary or delete files.
"""

from django.db import transaction

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cloudinary_cleanup import (
    build_cloudinary_cleanup_plan,
)
from users.deletion.asset_policy import get_asset_policy
from users.deletion.asset_reference_validation import (
    validate_asset_reference,
    AssetReferenceValidationError,
)


@transaction.atomic
def queue_account_deletion_assets(deletion_request):
    if deletion_request.status not in ("pending", "processing"):
        raise ValueError(
            "Only pending or processing deletion requests can queue assets."
        )

    user = deletion_request.user

    if user is None:
        raise ValueError(
            "Deletion request has no associated user."
        )

    if deletion_request.account_type != user.user_type:
        raise ValueError("Account type mismatch.")

    plan = build_cloudinary_cleanup_plan(user)
    queued_jobs = []

    for asset in plan["assets"]:
        reference = asset["storage_reference"]

        policy = get_asset_policy(
            asset["owner"],
            asset["field"],
        )

        try:
            validation = validate_asset_reference(
                asset["owner"],
                asset["field"],
                reference,
            )
        except (ValueError, AssetReferenceValidationError) as exc:
            raise ValueError(
                f"Invalid asset reference for {asset['field']}: {exc}"
            ) from exc

        if validation["storage"] != policy["storage"]:
            raise ValueError(
                "Asset storage type does not match the cleanup policy."
            )

        if validation["resource_type"] != policy["resource_type"]:
            raise ValueError(
                "Asset resource type does not match the cleanup policy."
            )

        job, created = AccountDeletionAsset.objects.get_or_create(
            deletion_request=deletion_request,
            owner_type=asset["owner"],
            field_name=asset["field"],
            defaults={
                "storage_reference": reference,
                "resource_type": policy["resource_type"],
                "status": "pending",
            },
        )

        if not created and job.storage_reference != reference:
            raise ValueError(
                "Asset reference changed after cleanup was queued."
            )

        if not created and job.resource_type != policy["resource_type"]:
            raise ValueError(
                "Asset resource type does not match the cleanup policy."
            )

        queued_jobs.append(job)

    return queued_jobs
