"""
Storage adapters for account deletion.

Real storage deletion is available through an explicitly
injected adapter. The default adapter remains disabled.

Tests should use FakeStorageAdapter.
"""

import cloudinary

from django.core.files.storage import default_storage

from users.deletion.asset_policy import get_asset_policy
from users.deletion.asset_reference_validation import (
    validate_asset_reference,
    AssetReferenceValidationError,
)


class StorageCleanupError(Exception):
    """Storage deletion failed or could not be confirmed."""


class DisabledStorageAdapter:
    """Default adapter: never deletes external files."""

    def delete(
        self,
        reference,
        *,
        resource_type,
        storage,
        owner_type=None,
        field_name=None,
    ):
        raise StorageCleanupError(
            "External storage deletion is disabled."
        )


class CloudinaryStorageAdapter:
    """
    Production storage adapter.

    django:
        Uses Django's configured default storage backend.

    cloudinary:
        Uses Cloudinary's uploader API directly.
    """

    def delete(self, reference, *, resource_type, storage,
               owner_type=None, field_name=None):

        if not owner_type or not field_name:
            raise StorageCleanupError(
                "Asset ownership information is required."
            )

        try:
            policy = get_asset_policy(owner_type, field_name)

            validation = validate_asset_reference(
                owner_type,
                field_name,
                reference,
            )

        except (
            ValueError,
            TypeError,
            AssetReferenceValidationError,
        ) as exc:
            raise StorageCleanupError(
                "Asset reference validation failed."
            ) from exc

        if (
            policy["storage"] != storage
            or policy["resource_type"] != resource_type
            or validation["reference"] != reference
        ):
            raise StorageCleanupError(
                "Asset storage configuration mismatch."
            )

        try:
            if storage == "django":

                deleted = default_storage.delete(reference)

                if deleted is not True:
                    raise StorageCleanupError(
                        "Django storage did not confirm deletion."
                    )

            elif storage == "cloudinary":

                response = cloudinary.uploader.destroy(
                    reference,
                    invalidate=True,
                    resource_type=resource_type,
                    type="upload",
                )

                if (
                    not isinstance(response, dict)
                    or response.get("result") != "ok"
                ):
                    raise StorageCleanupError(
                        "Cloudinary did not confirm deletion."
                    )

            else:
                raise StorageCleanupError(
                    "Unsupported storage backend."
                )

        except StorageCleanupError:
            raise

        except Exception as exc:
            raise StorageCleanupError(
                "Storage deletion failed or outcome is uncertain."
            ) from exc

        return {
            "result": "ok",
            "storage": storage,
            "resource_type": resource_type,
        }


class FakeStorageAdapter:
    """
    Test-only adapter.

    Simulates deletion without contacting Cloudinary.
    """

    def __init__(self, *, fail=False):
        self.fail = fail
        self.deleted_references = []

    def delete(
        self,
        reference,
        *,
        resource_type,
        storage,
        owner_type=None,
        field_name=None,
    ):

        if self.fail:
            raise StorageCleanupError(
                "Simulated storage deletion failure."
            )

        self.deleted_references.append({
            "reference": reference,
            "resource_type": resource_type,
            "storage": storage,
        })

        return {"result": "ok"}
