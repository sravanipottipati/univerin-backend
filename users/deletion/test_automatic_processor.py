from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest
from users.deletion.processor import process_automatic_deletion_request


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class AutomaticDeletionProcessorTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876548801",
            password="TestPassword123!",
            full_name="Automatic Deletion Buyer",
            user_type="buyer",
        )
        self.request = AccountDeletionRequest.objects.create(
            user=self.buyer,
            account_type="buyer",
            status="pending",
        )

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=False)
    def test_feature_flag_blocks_automatic_deletion(self):
        with self.assertRaises(PermissionError):
            process_automatic_deletion_request(self.request.pk)

        self.buyer.refresh_from_db()
        self.request.refresh_from_db()

        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(self.request.status, "pending")

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_eligible_buyer_is_automatically_deleted(self):
        result = process_automatic_deletion_request(self.request.pk)

        self.buyer.refresh_from_db()
        self.request.refresh_from_db()

        self.assertEqual(result.status, "completed")
        self.assertEqual(self.request.status, "completed")
        self.assertTrue(self.buyer.is_deleted)
        self.assertFalse(self.buyer.is_active)
        self.assertIsNone(self.buyer.phone_number)
        self.assertIsNotNone(self.request.completed_at)

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_restricted_reviewer_cannot_be_automatically_deleted(self):
        reviewer = User.objects.create_user(
            phone_number="9999999991",
            password="TestPassword123!",
            full_name="Protected Reviewer",
            user_type="buyer",
        )
        reviewer_request = AccountDeletionRequest.objects.create(
            user=reviewer,
            account_type="buyer",
            status="pending",
        )

        with self.assertRaises(ValueError):
            process_automatic_deletion_request(reviewer_request.pk)

        reviewer.refresh_from_db()
        reviewer_request.refresh_from_db()

        self.assertTrue(reviewer.is_active)
        self.assertFalse(reviewer.is_deleted)
        self.assertEqual(reviewer_request.status, "pending")

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_eligible_vendor_is_automatically_deleted(self):
        from vendors.models import Vendor

        vendor_user = User.objects.create_user(
            phone_number="9876548802",
            password="TestPassword123!",
            full_name="Automatic Vendor",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Test Shop",
            category="supermarket",
            phone_number="9876548802",
            address="Test Address",
            town="Test Town",
            bank_account_name="Test Vendor",
            bank_account_number="1234567890",
            bank_ifsc_code="TEST0001234",
            gstin="22AAAAA0000A1Z5",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=vendor_user,
            account_type="vendor",
            status="pending",
        )

        result = process_automatic_deletion_request(deletion_request.pk)

        vendor_user.refresh_from_db()
        vendor.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertEqual(result.status, "completed")
        self.assertEqual(deletion_request.status, "completed")
        self.assertTrue(vendor_user.is_deleted)
        self.assertFalse(vendor_user.is_active)
        self.assertIsNone(vendor_user.phone_number)
        self.assertIsNone(vendor.bank_account_number)
        self.assertIsNone(vendor.gstin)
        self.assertEqual(vendor.shop_name, "Deleted Vendor")

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_eligible_delivery_partner_is_automatically_deleted(self):
        from delivery_partner.models import DeliveryPartner

        partner_user = User.objects.create_user(
            phone_number="9876548803",
            password="TestPassword123!",
            full_name="Automatic Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=partner_user,
            vehicle_type="bike",
            vehicle_number="TEST1234",
            aadhaar_number="123456789012",
            pan_number="ABCDE1234F",
            driving_licence_number="TESTDL123",
            current_latitude=17.4,
            current_longitude=78.5,
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=partner_user,
            account_type="delivery_partner",
            status="pending",
        )

        result = process_automatic_deletion_request(deletion_request.pk)

        partner_user.refresh_from_db()
        partner.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertEqual(result.status, "completed")
        self.assertEqual(deletion_request.status, "completed")
        self.assertTrue(partner_user.is_deleted)
        self.assertFalse(partner_user.is_active)
        self.assertIsNone(partner_user.phone_number)
        self.assertIsNone(partner.aadhaar_number)
        self.assertIsNone(partner.pan_number)
        self.assertIsNone(partner.vehicle_number)
        self.assertIsNone(partner.current_latitude)
        self.assertIsNone(partner.current_longitude)

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_delivery_partner_with_document_is_not_automatically_deleted(self):
        from delivery_partner.models import DeliveryPartner
        from users.deletion.processor import DeletionBlockedError

        partner_user = User.objects.create_user(
            phone_number="9876548804",
            password="TestPassword123!",
            full_name="Protected Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=partner_user,
            aadhaar_number="123456789012",
            aadhaar_document="univerin/dp_documents/aadhaar/test-document",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=partner_user,
            account_type="delivery_partner",
            status="pending",
        )

        with self.assertRaises(DeletionBlockedError):
            process_automatic_deletion_request(deletion_request.pk)

        partner_user.refresh_from_db()
        partner.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(partner.aadhaar_number, "123456789012")
        self.assertTrue(partner.aadhaar_document)
        self.assertEqual(deletion_request.status, "pending")
        self.assertIsNone(deletion_request.completed_at)

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_vendor_with_wallet_balance_is_not_automatically_deleted(self):
        from decimal import Decimal
        from vendors.models import Vendor
        from users.deletion.processor import DeletionBlockedError

        vendor_user = User.objects.create_user(
            phone_number="9876548805",
            password="TestPassword123!",
            full_name="Vendor With Balance",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Balance Test Shop",
            category="supermarket",
            phone_number="9876548805",
            address="Test Address",
            town="Test Town",
            wallet_balance=Decimal("250.00"),
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=vendor_user,
            account_type="vendor",
            status="pending",
        )

        with self.assertRaises(DeletionBlockedError):
            process_automatic_deletion_request(deletion_request.pk)

        vendor_user.refresh_from_db()
        vendor.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(vendor_user.is_active)
        self.assertFalse(vendor_user.is_deleted)
        self.assertEqual(vendor.wallet_balance, Decimal("250.00"))
        self.assertEqual(deletion_request.status, "pending")
        self.assertIsNone(deletion_request.completed_at)

    @override_settings(
        ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
        ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED=False,
        TESTING_ACCOUNT_DELETION_CLEANUP=False,
    )
    def test_production_execution_flag_blocks_direct_processing(self):
        with self.assertRaises(PermissionError):
            process_automatic_deletion_request(self.request.pk)

        self.buyer.refresh_from_db()
        self.request.refresh_from_db()

        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(self.request.status, "pending")
