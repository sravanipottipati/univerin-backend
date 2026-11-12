"""
Conservative database reference checks for account deletion.

No external files are deleted here.

This checks exact stored references across known upload fields.
It does not prove Cloudinary ownership or detect aliases that
refer to the same asset using different identifiers.
"""

from django.apps import apps

from users.deletion.asset_policy import ASSET_POLICY


UPLOAD_FIELDS = {
    "users.User": ("profile_photo",),
    "vendors.Vendor": (
        "fssai_certificate",
        "banner_image",
    ),
    "vendors.Product": ("image",),
    "delivery_partner.DeliveryPartner": (
        "aadhaar_document",
        "pan_document",
        "driving_licence_document",
        "selfie_photo",
    ),
    "orders.Refund": ("photo",),
}


def find_other_asset_references(job):
    """
    Return database references matching the queued asset.

    The originating field is excluded only when its model,
    record ID, and field name all match.
    """
    request = job.deletion_request
    user = request.user

    if user is None:
        raise ValueError("Deletion request has no user.")

    if (job.owner_type, job.field_name) not in ASSET_POLICY:
        raise ValueError("Asset field is not approved.")

    if job.owner_type == "user":
        origin = user
    elif job.owner_type == "vendor":
        origin = getattr(user, "vendor", None)
    elif job.owner_type == "delivery_partner":
        origin = getattr(user, "delivery_partner", None)
    else:
        raise ValueError("Unsupported asset owner.")

    if origin is None:
        raise ValueError("Asset owner record is missing.")

    reference = job.storage_reference
    matches = []

    for model_label, field_names in UPLOAD_FIELDS.items():
        model = apps.get_model(model_label)

        for field_name in field_names:
            records = model.objects.filter(
                **{field_name: reference}
            )

            if model == type(origin) and field_name == job.field_name:
                records = records.exclude(pk=origin.pk)

            for record_id in records.values_list("pk", flat=True):
                matches.append({
                    "model": model_label,
                    "field": field_name,
                    "record_id": str(record_id),
                })

    return matches
