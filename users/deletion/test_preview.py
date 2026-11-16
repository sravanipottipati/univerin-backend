from django.test import TestCase

from users.models import User
from users.deletion.preview import preview_account_deletion


class AccountDeletionPreviewTests(TestCase):

    def test_buyer_preview_without_related_records(self):
        user = User.objects.create_user(
            phone_number="9876544444",
            password=None,
            full_name="Preview Test Buyer",
            user_type="buyer",
        )

        result = preview_account_deletion(user)

        self.assertEqual(result["account_type"], "buyer")
        self.assertTrue(result["can_proceed"])
        self.assertTrue(result["preview_only"])
        self.assertEqual(result["blockers"], [])

        expected_counts = [
            "saved_addresses",
            "buyer_orders",
            "refund_requests",
            "razorpay_checkouts",
            "assigned_deliveries",
            "vendor_profiles",
            "delivery_partner_profiles",
            "vendor_orders",
        ]

        for key in expected_counts:
            self.assertEqual(result["record_counts"][key], 0)


class AutomaticDeletionPreviewCommandTests(TestCase):

    def test_unresolved_cleanup_job_requires_review(self):
        from io import StringIO
        from django.core.management import call_command
        from users.deletion.service import create_deletion_request

        buyer = User.objects.create_user(
            phone_number="9876544455",
            password="TestPassword123!",
            full_name="Cleanup Preview Buyer",
            user_type="buyer",
        )

        deletion_request = create_deletion_request(buyer)["request"]

        output = StringIO()

        from users.deletion.cleanup_models import AccountDeletionAsset

        cleanup_job = AccountDeletionAsset.objects.create(
            deletion_request=deletion_request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="test/sample-image",
            resource_type="image",
            status="pending",
        )

        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        cleanup_job.refresh_from_db()
        self.assertEqual(cleanup_job.status, "pending")

        result = output.getvalue()

        self.assertIn("REVIEW", result)
        self.assertIn(
            "Unresolved asset cleanup jobs require review.",
            result,
        )
        self.assertIn("0 candidates", result)

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_eligible_buyer_is_preliminary_candidate(self):
        from io import StringIO
        from django.core.management import call_command
        from users.deletion.service import create_deletion_request

        buyer = User.objects.create_user(
            phone_number="9876544466",
            password="TestPassword123!",
            full_name="Candidate Preview Buyer",
            user_type="buyer",
        )

        deletion_request = create_deletion_request(buyer)["request"]

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("CANDIDATE", result)
        self.assertIn("1 candidates", result)
        self.assertIn("DRY RUN ONLY", result)

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_restricted_reviewer_account_requires_review(self):
        from io import StringIO
        from django.core.management import call_command
        from users.models import AccountDeletionRequest

        reviewer = User.objects.create_user(
            phone_number="9999999991",
            password="TestPassword123!",
            full_name="Protected Reviewer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=reviewer,
            account_type="buyer",
            status="pending",
        )

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("REVIEW", result)
        self.assertIn("0 candidates", result)
        self.assertIn("1 requiring review", result)

        reviewer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(reviewer.is_active)
        self.assertFalse(reviewer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_vendor_missing_profile_requires_review(self):
        from io import StringIO
        from django.core.management import call_command
        from users.deletion.service import create_deletion_request

        vendor_user = User.objects.create_user(
            phone_number="9876544477",
            password="TestPassword123!",
            full_name="Vendor Missing Profile",
            user_type="vendor",
        )

        deletion_request = create_deletion_request(
            vendor_user
        )["request"]

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("BLOCKED", result)
        self.assertIn("Vendor profile could not be verified.", result)
        self.assertIn("0 candidates", result)
        self.assertIn("1 blocked", result)

        vendor_user.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(vendor_user.is_active)
        self.assertFalse(vendor_user.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_delivery_partner_missing_profile_not_candidate(self):
        from io import StringIO
        from django.core.management import call_command
        from users.deletion.service import create_deletion_request

        partner_user = User.objects.create_user(
            phone_number="9876544488",
            password="TestPassword123!",
            full_name="Delivery Partner Missing Profile",
            user_type="delivery_partner",
        )

        deletion_request = create_deletion_request(
            partner_user
        )["request"]

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("0 candidates", result)
        self.assertIn("delivery_partner", result)
        self.assertTrue(
            "BLOCKED" in result or "REVIEW" in result
        )

        partner_user.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_delivery_partner_with_kyc_document_not_candidate(self):
        from io import StringIO
        from django.core.management import call_command
        from delivery_partner.models import DeliveryPartner
        from users.deletion.service import create_deletion_request

        partner_user = User.objects.create_user(
            phone_number="9876544499",
            password="TestPassword123!",
            full_name="Delivery Partner KYC Test",
            user_type="delivery_partner",
        )

        DeliveryPartner.objects.create(
            user=partner_user,
            vehicle_type="bike",
            aadhaar_document="test/deletion-preview-aadhaar",
        )

        deletion_request = create_deletion_request(
            partner_user
        )["request"]

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("delivery_partner", result)
        self.assertIn("0 candidates", result)
        self.assertRegex(result, r"BLOCKED|REVIEW")

        partner_user.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    def test_delivery_partner_with_historical_order_not_candidate(self):
        from io import StringIO
        from django.core.management import call_command
        from delivery_partner.models import DeliveryPartner
        from vendors.models import Vendor
        from orders.models import Order
        from users.deletion.service import create_deletion_request

        buyer = User.objects.create_user(
            phone_number="9876544501",
            password=None,
            full_name="Historical Order Buyer",
            user_type="buyer",
        )

        vendor_user = User.objects.create_user(
            phone_number="9876544502",
            password=None,
            full_name="Historical Order Vendor",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Deletion Test Shop",
            category="restaurant",
            phone_number="9876544502",
            address="Test Address",
            town="Test Town",
        )

        partner_user = User.objects.create_user(
            phone_number="9876544503",
            password=None,
            full_name="Historical Order Delivery Partner",
            user_type="delivery_partner",
        )

        DeliveryPartner.objects.create(
            user=partner_user,
            vehicle_type="bike",
        )

        Order.objects.create(
            buyer=buyer,
            vendor=vendor,
            total_amount="100.00",
            delivery_address="Test Delivery Address",
            status="delivered",
            delivery_partner=partner_user,
            dp_status="delivered",
        )

        deletion_request = create_deletion_request(
            partner_user
        )["request"]

        output = StringIO()
        call_command(
            "preview_automatic_deletions",
            stdout=output,
        )

        result = output.getvalue()

        self.assertIn("delivery_partner", result)
        self.assertIn("0 candidates", result)
        self.assertRegex(result, r"BLOCKED|REVIEW")

        partner_user.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
