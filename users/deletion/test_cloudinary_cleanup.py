from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from users.deletion.cloudinary_cleanup import (
    build_cloudinary_cleanup_plan,
)


class CloudinaryCleanupPlanTests(TestCase):

    def test_buyer_without_files(self):
        user = User.objects.create_user(
            phone_number="9876549201",
            password="TestPassword123!",
            full_name="Test Buyer",
            user_type="buyer",
        )

        plan = build_cloudinary_cleanup_plan(user)

        self.assertEqual(plan["asset_count"], 0)
        self.assertFalse(plan["ready_for_cleanup"])

    def test_vendor_certificate_inventory(self):
        user = User.objects.create_user(
            phone_number="9876549202",
            password="TestPassword123!",
            full_name="Test Vendor",
            user_type="vendor",
        )

        Vendor.objects.create(
            user=user,
            shop_name="Test Shop",
            category="supermarket",
            phone_number="9876549202",
            address="Test Address",
            town="Test Town",
            fssai_certificate="fssai_certificates/test.jpg",
        )

        plan = build_cloudinary_cleanup_plan(user)

        self.assertEqual(plan["asset_count"], 1)
        self.assertEqual(
            plan["assets"][0]["field"],
            "fssai_certificate",
        )
        self.assertFalse(plan["ready_for_cleanup"])

    def test_delivery_partner_document_inventory(self):
        user = User.objects.create_user(
            phone_number="9876549203",
            password="TestPassword123!",
            full_name="Test Partner",
            user_type="delivery_partner",
        )

        DeliveryPartner.objects.create(
            user=user,
            aadhaar_document="univerin/dp_documents/aadhaar/test",
            pan_document="univerin/dp_documents/pan/test",
        )

        plan = build_cloudinary_cleanup_plan(user)

        self.assertEqual(plan["asset_count"], 2)

        fields = {
            asset["field"]
            for asset in plan["assets"]
        }

        self.assertEqual(
            fields,
            {"aadhaar_document", "pan_document"},
        )
        self.assertFalse(plan["ready_for_cleanup"])
