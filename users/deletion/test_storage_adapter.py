from django.test import SimpleTestCase

from users.deletion.storage_adapter import (
    DisabledStorageAdapter,
    FakeStorageAdapter,
    StorageCleanupError,
)


class StorageAdapterTests(SimpleTestCase):

    def test_real_storage_deletion_is_disabled(self):
        adapter = DisabledStorageAdapter()

        with self.assertRaises(StorageCleanupError):
            adapter.delete(
                "profile_photos/test.jpg",
                resource_type="image",
                storage="django",
            )

    def test_fake_adapter_simulates_success(self):
        adapter = FakeStorageAdapter()

        result = adapter.delete(
            "profile_photos/test.jpg",
            resource_type="image",
            storage="django",
        )

        self.assertEqual(result["result"], "ok")
        self.assertEqual(len(adapter.deleted_references), 1)

    def test_fake_adapter_simulates_failure(self):
        adapter = FakeStorageAdapter(fail=True)

        with self.assertRaises(StorageCleanupError):
            adapter.delete(
                "profile_photos/test.jpg",
                resource_type="image",
                storage="django",
            )

        self.assertEqual(adapter.deleted_references, [])
