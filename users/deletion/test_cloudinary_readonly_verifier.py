from unittest.mock import Mock

from django.test import SimpleTestCase

from users.deletion.cloudinary_readonly_verifier import (
    CloudinaryReadOnlyVerifier,
)


class CloudinaryReadOnlyVerifierTests(SimpleTestCase):

    def setUp(self):
        self.client = Mock()
        self.verifier = CloudinaryReadOnlyVerifier(
            client=self.client
        )
        self.reference = "univerin/shop_banners/banner123"

    def test_matching_resource_exists(self):
        self.client.resource.return_value = {
            "public_id": self.reference,
            "resource_type": "image",
            "type": "upload",
        }

        result = self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "exists")
        self.assertEqual(result.provider, "cloudinary")

        self.client.resource.assert_called_once_with(
            self.reference,
            resource_type="image",
            type="upload",
        )

    def test_mismatched_public_id_is_unknown(self):
        self.client.resource.return_value = {
            "public_id": "another/banner",
            "resource_type": "image",
            "type": "upload",
        }

        result = self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "unknown")

    def test_mismatched_resource_type_is_unknown(self):
        self.client.resource.return_value = {
            "public_id": self.reference,
            "resource_type": "video",
            "type": "upload",
        }

        result = self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "unknown")

    def test_provider_exception_is_unknown(self):
        self.client.resource.side_effect = RuntimeError(
            "Simulated provider failure"
        )

        result = self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "unknown")

    def test_invalid_response_is_unknown(self):
        self.client.resource.return_value = None

        result = self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "unknown")


class CloudinaryInvalidReferenceTests(SimpleTestCase):

    def setUp(self):
        self.client = Mock()
        self.verifier = CloudinaryReadOnlyVerifier(
            client=self.client
        )

    def assert_rejected_without_provider_call(self, reference):
        result = self.verifier.verify(
            reference,
            resource_type="image",
            storage="cloudinary",
        )

        self.assertEqual(result.state, "unknown")
        self.client.resource.assert_not_called()

    def test_url_rejected(self):
        self.assert_rejected_without_provider_call(
            "https://example.com/image.jpg"
        )

    def test_traversal_rejected(self):
        self.assert_rejected_without_provider_call(
            "univerin/shop_banners/../secret"
        )

    def test_whitespace_rejected(self):
        self.assert_rejected_without_provider_call(
            " univerin/shop_banners/banner123 "
        )

    def test_empty_reference_rejected(self):
        self.assert_rejected_without_provider_call("")


class CloudinaryNotFoundTests(SimpleTestCase):

    def setUp(self):
        self.client = Mock()
        self.verifier = CloudinaryReadOnlyVerifier(
            client=self.client
        )
        self.reference = "univerin/shop_banners/banner123"

    def verify(self):
        return self.verifier.verify(
            self.reference,
            resource_type="image",
            storage="cloudinary",
        )

    def test_not_found_reports_absent(self):
        from cloudinary.exceptions import NotFound

        self.client.resource.side_effect = NotFound(
            "Resource not found"
        )

        result = self.verify()

        self.assertEqual(result.state, "absent")
        self.assertEqual(result.provider, "cloudinary")

    def test_rate_limit_remains_unknown(self):
        from cloudinary.exceptions import RateLimited

        self.client.resource.side_effect = RateLimited(
            "Rate limit exceeded"
        )

        result = self.verify()

        self.assertEqual(result.state, "unknown")

    def test_bad_request_remains_unknown(self):
        from cloudinary.exceptions import BadRequest

        self.client.resource.side_effect = BadRequest(
            "Invalid request"
        )

        result = self.verify()

        self.assertEqual(result.state, "unknown")

    def test_general_error_remains_unknown(self):
        from cloudinary.exceptions import GeneralError

        self.client.resource.side_effect = GeneralError(
            "Provider unavailable"
        )

        result = self.verify()

        self.assertEqual(result.state, "unknown")
