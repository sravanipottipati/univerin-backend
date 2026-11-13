from django.test import SimpleTestCase
from cloudinary import CloudinaryResource

from users.deletion.asset_reference_validation import (
    validate_asset_reference,
)


class CloudinaryReferenceFormatTests(SimpleTestCase):

    def test_cloudinary_resource_serialization(self):
        resource = CloudinaryResource(
            public_id="univerin/shop_banners/banner123",
            resource_type="image",
            type="upload",
            version=1234567890,
            format="jpg",
        )

        self.assertEqual(
            resource.get_prep_value(),
            "image/upload/v1234567890/"
            "univerin/shop_banners/banner123.jpg",
        )

    def test_cleanup_reference_uses_public_id(self):
        resource = CloudinaryResource(
            public_id="univerin/shop_banners/banner123",
            resource_type="image",
            type="upload",
            version=1234567890,
            format="jpg",
        )

        reference = (
            getattr(resource, "public_id", None)
            or getattr(resource, "name", None)
            or str(resource)
        )

        self.assertEqual(
            reference,
            "univerin/shop_banners/banner123",
        )

    def test_public_id_passes_current_validator(self):
        result = validate_asset_reference(
            "vendor",
            "banner_image",
            "univerin/shop_banners/banner123",
        )

        self.assertTrue(result["reference_valid"])
        self.assertFalse(result["ownership_verified"])
        self.assertFalse(result["deletion_authorized"])
