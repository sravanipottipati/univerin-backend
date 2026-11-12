from unittest.mock import patch

from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request


class WorkerRollbackTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone_number="9876549700",
            password="TestPassword123!",
            full_name="Test Admin",
            user_type="admin",
        )

    def test_vendor_rollback(self):
        user = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Vendor Owner",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=user,
            shop_name="Original Shop",
            category="supermarket",
            phone_number="9876549701",
            address="Original Address",
            town="Original Town",
            bank_account_number="123456789",
        )

        deletion = create_deletion_request(user)["request"]

        with patch(
            "users.deletion.worker_erasure._erase_common_user_data",
            side_effect=RuntimeError("Simulated failure"),
        ):
            with self.assertRaises(RuntimeError):
                process_deletion_request(
                    deletion.pk,
                    approved_by=self.admin,
                )

        user.refresh_from_db()
        vendor.refresh_from_db()
        deletion.refresh_from_db()

        self.assertFalse(user.is_deleted)
        self.assertTrue(user.is_active)
        self.assertEqual(user.phone_number, "9876549701")
        self.assertEqual(vendor.shop_name, "Original Shop")
        self.assertEqual(vendor.bank_account_number, "123456789")
        self.assertEqual(deletion.status, "pending")

    def test_delivery_partner_rollback(self):
        user = User.objects.create_user(
            phone_number="9876549702",
            password="TestPassword123!",
            full_name="Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=user,
            aadhaar_number="123412341234",
            vehicle_number="AP01AB1234",
        )

        deletion = create_deletion_request(user)["request"]

        with patch(
            "users.deletion.worker_erasure._erase_common_user_data",
            side_effect=RuntimeError("Simulated failure"),
        ):
            with self.assertRaises(RuntimeError):
                process_deletion_request(
                    deletion.pk,
                    approved_by=self.admin,
                )

        user.refresh_from_db()
        partner.refresh_from_db()
        deletion.refresh_from_db()

        self.assertFalse(user.is_deleted)
        self.assertTrue(user.is_active)
        self.assertEqual(user.phone_number, "9876549702")
        self.assertEqual(partner.aadhaar_number, "123412341234")
        self.assertEqual(partner.vehicle_number, "AP01AB1234")
        self.assertEqual(deletion.status, "pending")
