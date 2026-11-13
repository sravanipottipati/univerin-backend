"""
Conservative validation of account-deletion asset references.

This module performs no external operations.
Passing validation does not establish ownership or
authorize storage deletion.
"""

from users.deletion.asset_policy import get_asset_policy
from users.deletion.cloudinary_safety import (
    validate_cloudinary_reference,
)


CLOUDINARY_FIELD_FOLDERS = {
    ("vendor", "banner_image"):
        "univerin/shop_banners",

    ("delivery_partner", "aadhaar_document"):
        "univerin/dp_documents/aadhaar",

    ("delivery_partner", "pan_document"):
        "univerin/dp_documents/pan",

    ("delivery_partner", "driving_licence_document"):
        "univerin/dp_documents/dl",

    ("delivery_partner", "selfie_photo"):
        "univerin/dp_documents/selfie",
}


class AssetReferenceValidationError(Exception):
    pass


def validate_asset_reference(
    owner_type,
    field_name,
    reference,
):
    policy = get_asset_policy(owner_type, field_name)

    if not validate_cloudinary_reference(reference):
        raise AssetReferenceValidationError(
            "Invalid asset reference."
        )

    if reference != reference.strip():
        raise AssetReferenceValidationError(
            "Asset reference contains surrounding whitespace."
        )

    if policy["storage"] == "cloudinary":
        expected_folder = CLOUDINARY_FIELD_FOLDERS.get(
            (owner_type, field_name)
        )

        if expected_folder is None:
            raise AssetReferenceValidationError(
                "Cloudinary field has no approved folder."
            )

        if not reference.startswith(expected_folder + "/"):
            raise AssetReferenceValidationError(
                "Asset reference is outside the approved folder."
            )

    elif policy["storage"] != "django":
        raise AssetReferenceValidationError(
            "Unsupported storage type."
        )

    return {
        "owner_type": owner_type,
        "field_name": field_name,
        "reference": reference,
        "storage": policy["storage"],
        "resource_type": policy["resource_type"],
        "reference_valid": True,
        "ownership_verified": False,
        "deletion_authorized": False,
    }
