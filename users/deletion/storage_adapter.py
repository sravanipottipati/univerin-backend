"""
Storage adapters for account deletion.

Production deletion is intentionally disabled.
Tests may inject a fake adapter.
"""


class StorageCleanupError(Exception):
    pass


class DisabledStorageAdapter:
    """Default adapter: never deletes external files."""

    def delete(self, reference, *, resource_type, storage):
        raise StorageCleanupError(
            "External storage deletion is disabled."
        )


class FakeStorageAdapter:
    """
    Test-only adapter.

    Simulates deletion without contacting Cloudinary.
    """

    def __init__(self, *, fail=False):
        self.fail = fail
        self.deleted_references = []

    def delete(self, reference, *, resource_type, storage):
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
