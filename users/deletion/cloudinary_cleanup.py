"""
Read-only inventory of account-related uploaded files.

This module does not delete files or make external API calls.
"""


def build_cloudinary_cleanup_plan(user):
    assets = []

    def add_asset(owner, field_name, field):
        if not field:
            return

        # Django ImageField uses .name.
        # CloudinaryField may return a CloudinaryResource
        # whose identifier is available through public_id.
        reference = (
            getattr(field, "public_id", None)
            or getattr(field, "name", None)
            or str(field)
        )

        if reference:
            assets.append({
                "owner": owner,
                "field": field_name,
                "storage_reference": str(reference),
                "requires_cleanup": True,
            })

    add_asset("user", "profile_photo", user.profile_photo)

    if user.user_type == "vendor":
        vendor = getattr(user, "vendor", None)

        if vendor is not None:
            add_asset(
                "vendor",
                "fssai_certificate",
                vendor.fssai_certificate,
            )
            add_asset(
                "vendor",
                "banner_image",
                vendor.banner_image,
            )

    elif user.user_type == "delivery_partner":
        partner = getattr(user, "delivery_partner", None)

        if partner is not None:
            for field_name in (
                "aadhaar_document",
                "pan_document",
                "driving_licence_document",
                "selfie_photo",
            ):
                add_asset(
                    "delivery_partner",
                    field_name,
                    getattr(partner, field_name),
                )

    return {
        "account_type": user.user_type,
        "asset_count": len(assets),
        "assets": assets,
        "ready_for_cleanup": False,
    }
