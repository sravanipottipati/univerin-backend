from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request


class WorkerErasureSuccessTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="9876549800",
            password="TestPassword123!",
            full_name="Test Admin",
            user_type="admin",
        )

    def test_vendor_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549801",
            password="TestPassword123!",
            full_name="Vendor Owner",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=user,
            shop_name="Test Grocery",
            category="supermarket",
            phone_number="9876549801",
            address="Private Street",
            town="Test Town",
            state="Telangana",
            bank_account_number="123456789",
            pan="ABCDE1234F",
        )

        deletion = create_deletion_request(user)["request"]

        process_deletion_request(
            deletion.pk,
            approved_by=self.admin,
        )

        user.refresh_from_db()
        vendor.refresh_from_db()
        deletion.refresh_from_db()

        self.assertTrue(user.is_deleted)
        self.assertFalse(user.is_active)
        self.assertIsNone(user.phone_number)
        self.assertFalse(user.has_usable_password())

        self.assertIsNone(vendor.bank_account_number)
        self.assertIsNone(vendor.pan)
        self.assertEqual(vendor.shop_name, "Deleted Vendor")
        self.assertEqual(vendor.address, "")
        self.assertEqual(vendor.state, "")
        self.assertFalse(vendor.is_open)
        self.assertEqual(deletion.status, "completed")

    def test_delivery_partner_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549802",
            password="TestPassword123!",
            full_name="Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=user,
            vehicle_type="bike",
            vehicle_number="AP01AB1234",
            aadhaar_number="123412341234",
            pan_number="ABCDE1234F",
            current_latitude=17.4,
            current_longitude=78.5,
        )

        deletion = create_deletion_request(user)["request"]

        process_deletion_request(
            deletion.pk,
            approved_by=self.admin,
        )

        user.refresh_from_db()
        partner.refresh_from_db()
        deletion.refresh_from_db()

        self.assertTrue(user.is_deleted)
        self.assertFalse(user.is_active)
        self.assertIsNone(user.phone_number)
        self.assertFalse(user.has_usable_password())

        self.assertIsNone(partner.aadhaar_number)
        self.assertIsNone(partner.pan_number)
        self.assertIsNone(partner.vehicle_number)
        self.assertIsNone(partner.current_latitude)
        self.assertIsNone(partner.current_longitude)
        self.assertFalse(partner.is_online)
        self.assertEqual(deletion.status, "completed")
