"""
Read-only origin reference validation for account deletion.

This module does not access external storage or delete assets.
"""

from users.deletion.asset_policy import get_asset_policy
from users.deletion.asset_ownership import (
    find_other_asset_references,
)


class OriginReferenceError(Exception):
    pass


def validate_origin_reference(job):
    try:
        policy = get_asset_policy(
            job.owner_type,
            job.field_name,
        )
    except ValueError:
        raise OriginReferenceError(
            "Asset field is not approved."
        ) from None

    if job.resource_type != policy["resource_type"]:
        raise OriginReferenceError(
            "Asset resource type does not match policy."
        )

    request = job.deletion_request
    user = request.user

    if user is None:
        raise OriginReferenceError(
            "Deletion request has no user."
        )

    if job.owner_type == "user":
        owner = user
    elif job.owner_type == "vendor":
        owner = getattr(user, "vendor", None)
    elif job.owner_type == "delivery_partner":
        owner = getattr(user, "delivery_partner", None)
    else:
        owner = None

    if owner is None:
        raise OriginReferenceError(
            "Asset owner is missing."
        )

    # Fetch the current value from the database rather than
    # relying on an existing in-memory model instance.
    try:
        owner = type(owner).objects.get(pk=owner.pk)
    except type(owner).DoesNotExist:
        raise OriginReferenceError(
            "Asset owner no longer exists."
        ) from None

    field = getattr(owner, job.field_name)

    reference = (
        getattr(field, "public_id", None)
        or getattr(field, "name", None)
        or str(field)
    )

    if not reference or reference != job.storage_reference:
        raise OriginReferenceError(
            "Original asset reference is missing or changed."
        )

    # Exact-reference ownership check across known upload fields.
    # This does not establish exclusive ownership in Cloudinary.
    try:
        other_references = find_other_asset_references(job)
    except (ValueError, LookupError) as exc:
        raise OriginReferenceError(
            "Asset reference ownership could not be verified."
        ) from exc

    if other_references:
        raise OriginReferenceError(
            "Asset reference is shared by another record."
        )

    return True
