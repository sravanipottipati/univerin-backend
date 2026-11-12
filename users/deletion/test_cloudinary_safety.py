from django.test import SimpleTestCase

from users.deletion.cloudinary_safety import (
    validate_cloudinary_reference,
)


class CloudinarySafetyTests(SimpleTestCase):

    def test_valid_reference(self):
        self.assertTrue(
            validate_cloudinary_reference(
                "univerin/dp_documents/aadhaar/example"
            )
        )

    def test_rejects_urls(self):
        self.assertFalse(
            validate_cloudinary_reference(
                "https://res.cloudinary.com/example/image.jpg"
            )
        )

    def test_rejects_empty_reference(self):
        self.assertFalse(
            validate_cloudinary_reference("")
        )

    def test_rejects_path_traversal(self):
        self.assertFalse(
            validate_cloudinary_reference(
                "univerin/../other-user/document"
            )
        )

    def test_rejects_query_parameters(self):
        self.assertFalse(
            validate_cloudinary_reference(
                "univerin/document?delete=true"
            )
        )
