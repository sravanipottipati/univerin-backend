from unittest.mock import patch

from django.test import SimpleTestCase

from users.deletion.storage_adapter import (
    CloudinaryStorageAdapter,
    DisabledStorageAdapter,
    FakeStorageAdapter,
    StorageCleanupError,
)


class RealStorageAdapterTests(SimpleTestCase):

    def setUp(self):
        self.adapter = CloudinaryStorageAdapter()

    @patch("users.deletion.storage_adapter.default_storage.delete")
    def test_django_profile_photo_deletion(self, mock_delete):
        mock_delete.return_value = True

        result = self.adapter.delete(
            "profile_photos/test.jpg",
            resource_type="image",
            storage="django",
            owner_type="user",
            field_name="profile_photo",
        )

        mock_delete.assert_called_once_with(
            "profile_photos/test.jpg"
        )

        self.assertEqual(result["result"], "ok")

    @patch("users.deletion.storage_adapter.cloudinary.uploader.destroy")
    def test_cloudinary_vendor_banner_deletion(self, mock_destroy):
        mock_destroy.return_value = {"result": "ok"}

        result = self.adapter.delete(
            "univerin/shop_banners/banner123",
            resource_type="image",
            storage="cloudinary",
            owner_type="vendor",
            field_name="banner_image",
        )

        mock_destroy.assert_called_once_with(
            "univerin/shop_banners/banner123",
            invalidate=True,
            resource_type="image",
            type="upload",
        )

        self.assertEqual(result["result"], "ok")

    @patch("users.deletion.storage_adapter.default_storage.delete")
    def test_django_deletion_failure(self, mock_delete):
        mock_delete.return_value = False

        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "profile_photos/test.jpg",
                resource_type="image",
                storage="django",
                owner_type="user",
                field_name="profile_photo",
            )

    @patch("users.deletion.storage_adapter.cloudinary.uploader.destroy")
    def test_cloudinary_deletion_not_confirmed(self, mock_destroy):
        mock_destroy.return_value = {"result": "not found"}

        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "univerin/shop_banners/banner123",
                resource_type="image",
                storage="cloudinary",
                owner_type="vendor",
                field_name="banner_image",
            )

    @patch("users.deletion.storage_adapter.cloudinary.uploader.destroy")
    def test_cloudinary_api_exception(self, mock_destroy):
        mock_destroy.side_effect = Exception("Simulated API failure")

        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "univerin/shop_banners/banner123",
                resource_type="image",
                storage="cloudinary",
                owner_type="vendor",
                field_name="banner_image",
            )

    @patch("users.deletion.storage_adapter.cloudinary.uploader.destroy")
    def test_wrong_cloudinary_folder_rejected(self, mock_destroy):
        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "univerin/dp_documents/pan/document123",
                resource_type="image",
                storage="cloudinary",
                owner_type="vendor",
                field_name="banner_image",
            )

        mock_destroy.assert_not_called()

    @patch("users.deletion.storage_adapter.cloudinary.uploader.destroy")
    def test_wrong_storage_backend_rejected(self, mock_destroy):
        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "univerin/shop_banners/banner123",
                resource_type="image",
                storage="django",
                owner_type="vendor",
                field_name="banner_image",
            )

        mock_destroy.assert_not_called()

    def test_missing_ownership_information_rejected(self):
        with self.assertRaises(StorageCleanupError):
            self.adapter.delete(
                "profile_photos/test.jpg",
                resource_type="image",
                storage="django",
            )

    def test_disabled_adapter_still_blocks_real_deletion(self):
        adapter = DisabledStorageAdapter()

        with self.assertRaises(StorageCleanupError):
            adapter.delete(
                "profile_photos/test.jpg",
                resource_type="image",
                storage="django",
            )

    def test_fake_adapter_still_works(self):
        adapter = FakeStorageAdapter()

        result = adapter.delete(
            "profile_photos/test.jpg",
            resource_type="image",
            storage="django",
        )

        self.assertEqual(result["result"], "ok")
        self.assertEqual(len(adapter.deleted_references), 1)
