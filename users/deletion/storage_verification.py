"""
Read-only storage verification for account deletion reconciliation.

No real provider integration is enabled.
No storage deletion is performed.
"""

from dataclasses import dataclass


class StorageVerificationError(Exception):
    pass


@dataclass(frozen=True)
class StorageVerificationResult:
    state: str
    provider: str
    evidence_reference: str = ""


class DisabledStorageVerifier:
    def verify(self, reference, *, resource_type, storage):
        raise StorageVerificationError(
            "Production storage verification is not configured."
        )


class FakeStorageVerifier:
    """
    Test-only verifier.

    Simulates provider responses without contacting external storage.
    """

    def __init__(self, *, state="unknown"):
        if state not in ("exists", "absent", "unknown"):
            raise ValueError("Invalid verification state.")
        self.state = state

    def verify(self, reference, *, resource_type, storage):
        if not reference:
            raise StorageVerificationError(
                "Missing storage reference."
            )

        return StorageVerificationResult(
            state=self.state,
            provider=storage,
            evidence_reference="mock-verification",
        )
