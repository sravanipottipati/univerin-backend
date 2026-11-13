from django.test import SimpleTestCase

from users.deletion.asset_reference_validation import (
    AssetReferenceValidationError,
    validate_asset_reference,
)


class AssetReferenceValidationTests(SimpleTestCase):

    def test_valid_vendor_banner(self):
        result = validate_asset_reference(
            "vendor",
            "banner_image",
            "univerin/shop_banners/banner123",
        )
        self.assertTrue(result["reference_valid"])
        self.assertFalse(result["ownership_verified"])
        self.assertFalse(result["deletion_authorized"])

    def test_valid_delivery_partner_document(self):
        result = validate_asset_reference(
            "delivery_partner",
            "aadhaar_document",
            "univerin/dp_documents/aadhaar/document123",
        )
        self.assertTrue(result["reference_valid"])

    def test_valid_django_storage_key(self):
        result = validate_asset_reference(
            "user",
            "profile_photo",
            "profile_photos/photo123.jpg",
        )
        self.assertEqual(result["storage"], "django")
        self.assertFalse(result["ownership_verified"])

    def test_wrong_cloudinary_folder_rejected(self):
        with self.assertRaises(AssetReferenceValidationError):
            validate_asset_reference(
                "delivery_partner",
                "aadhaar_document",
                "univerin/dp_documents/pan/document123",
            )

    def test_external_url_rejected(self):
        with self.assertRaises(AssetReferenceValidationError):
            validate_asset_reference(
                "vendor",
                "banner_image",
                "https://example.com/image.jpg",
            )

    def test_path_traversal_rejected(self):
        with self.assertRaises(AssetReferenceValidationError):
            validate_asset_reference(
                "vendor",
                "banner_image",
                "univerin/shop_banners/../secret",
            )

    def test_whitespace_rejected(self):
        with self.assertRaises(AssetReferenceValidationError):
            validate_asset_reference(
                "vendor",
                "banner_image",
                " univerin/shop_banners/banner123 ",
            )

    def test_unsupported_field_rejected(self):
        with self.assertRaises(ValueError):
            validate_asset_reference(
                "vendor",
                "bank_account_number",
                "private/document123",
            )

    def test_no_deletion_authorization(self):
        result = validate_asset_reference(
            "delivery_partner",
            "selfie_photo",
            "univerin/dp_documents/selfie/photo123",
        )
        self.assertFalse(result["deletion_authorized"])
        self.assertFalse(result["ownership_verified"])
