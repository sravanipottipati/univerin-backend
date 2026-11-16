from django.test import TestCase

from users.models import User, AccountDeletionRequest
from vendors.models import Vendor

from users.deletion.cleanup_queue import queue_account_deletion_assets
from users.deletion.origin_reference_guard import (
    validate_origin_reference,
    OriginReferenceError,
)


class BuyerOriginReferenceGuardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549801",
            password="TestPassword123!",
            full_name="Guard Test Buyer",
            user_type="buyer",
        )

        self.user.profile_photo = "profile_photos/guard-test.jpg"
        self.user.save(update_fields=["profile_photo"])

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="pending",
        )

        self.job = queue_account_deletion_assets(
            self.request
        )[0]

    def test_original_reference_passes(self):
        self.assertTrue(validate_origin_reference(self.job))

    def test_replacement_reference_is_rejected(self):
        self.user.profile_photo = "profile_photos/replacement.jpg"
        self.user.save(update_fields=["profile_photo"])

        with self.assertRaises(OriginReferenceError):
            validate_origin_reference(self.job)

    def test_cleared_reference_is_rejected(self):
        self.user.profile_photo = None
        self.user.save(update_fields=["profile_photo"])

        with self.assertRaises(OriginReferenceError):
            validate_origin_reference(self.job)

    def test_shared_reference_is_rejected(self):
        other = User.objects.create_user(
            phone_number="9876549802",
            password="TestPassword123!",
            full_name="Other Buyer",
            user_type="buyer",
        )

        other.profile_photo = "profile_photos/guard-test.jpg"
        other.save(update_fields=["profile_photo"])

        with self.assertRaises(OriginReferenceError):
            validate_origin_reference(self.job)


class VendorOriginReferenceGuardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876549803",
            password="TestPassword123!",
            full_name="Guard Test Vendor",
            user_type="vendor",
        )

        self.vendor = Vendor.objects.create(
            user=self.user,
            shop_name="Guard Test Shop",
            category="supermarket",
            phone_number="9876549803",
            address="Test Street",
            town="Test Town",
            banner_image="univerin/shop_banners/guard-banner",
        )

        self.request = AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="vendor",
            status="pending",
        )

        jobs = queue_account_deletion_assets(self.request)

        self.job = next(
            job for job in jobs
            if job.field_name == "banner_image"
        )

    def test_original_cloudinary_reference_passes(self):
        self.assertTrue(validate_origin_reference(self.job))

    def test_replacement_cloudinary_reference_is_rejected(self):
        self.vendor.banner_image = (
            "univerin/shop_banners/replacement-banner"
        )
        self.vendor.save(update_fields=["banner_image"])

        with self.assertRaises(OriginReferenceError):
            validate_origin_reference(self.job)
