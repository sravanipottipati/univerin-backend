"""
Cloudinary Admin API verification logic.

This module does not instantiate a live Cloudinary client,
perform deletion, or integrate with production reconciliation.

A client must be explicitly supplied by the caller.
"""

from cloudinary.exceptions import NotFound

from users.deletion.storage_verification import (
    StorageVerificationResult,
)
from users.deletion.cloudinary_safety import (
    validate_cloudinary_reference,
)


class CloudinaryReadOnlyVerifier:
    def __init__(self, *, client):
        if client is None:
            raise ValueError("A verification client is required.")
        self._client = client

    def verify(self, reference, *, resource_type, storage):
        if (
            not validate_cloudinary_reference(reference)
            or reference != reference.strip()
            or resource_type != "image"
            or storage not in ("cloudinary", "django")
        ):
            return self._unknown(storage)

        try:
            response = self._client.resource(
                reference,
                resource_type=resource_type,
                type="upload",
            )
        except NotFound:
            # Observation only. This does not establish
            # ownership or authorize deletion/finalization.
            return StorageVerificationResult(
                state="absent",
                provider=storage,
                evidence_reference="cloudinary-admin-not-found",
            )
        except Exception:
            # Network, authentication, authorization, rate-limit,
            # and unexpected errors remain inconclusive.
            return self._unknown(storage)

        if not isinstance(response, dict):
            return self._unknown(storage)

        if (
            response.get("public_id") != reference
            or response.get("resource_type") != resource_type
            or response.get("type") != "upload"
        ):
            return self._unknown(storage)

        return StorageVerificationResult(
            state="exists",
            provider=storage,
            evidence_reference="cloudinary-admin-resource-match",
        )

    @staticmethod
    def _unknown(storage):
        return StorageVerificationResult(
            state="unknown",
            provider=storage,
            evidence_reference="cloudinary-verification-inconclusive",
        )
