"""
Account deletion asset policy.

Only explicitly listed account-level assets may be considered
for cleanup. This module does not delete external files.

Resource types describe the expected Cloudinary configuration;
they do not establish ownership or authorize deletion.
"""

ASSET_POLICY = {
    ("user", "profile_photo"): {
        "resource_type": "image",
        "storage": "django",
    },
    ("vendor", "fssai_certificate"): {
        "resource_type": "image",
        "storage": "django",
    },
    ("vendor", "banner_image"): {
        "resource_type": "image",
        "storage": "cloudinary",
    },
    ("delivery_partner", "aadhaar_document"): {
        "resource_type": "image",
        "storage": "cloudinary",
    },
    ("delivery_partner", "pan_document"): {
        "resource_type": "image",
        "storage": "cloudinary",
    },
    ("delivery_partner", "driving_licence_document"): {
        "resource_type": "image",
        "storage": "cloudinary",
    },
    ("delivery_partner", "selfie_photo"): {
        "resource_type": "image",
        "storage": "cloudinary",
    },
}


def get_asset_policy(owner_type, field_name):
    policy = ASSET_POLICY.get((owner_type, field_name))

    if policy is None:
        raise ValueError(
            "Asset field is not approved for account cleanup."
        )

    return policy
