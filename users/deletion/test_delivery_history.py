from decimal import Decimal

from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from orders.models import Order

from users.deletion.service import create_deletion_request
from users.deletion.processor import process_deletion_request
from users.deletion.worker_erasure import WorkerErasureNotReadyError
from users.deletion.worker_erasure_plan import (
    build_delivery_partner_erasure_plan,
)


class DeliveryHistoryProtectionTests(TestCase):

    def test_historical_delivery_blocks_erasure(self):
        admin = User.objects.create_superuser(
            phone_number="9876549400",
            password="TestPassword123!",
            full_name="Test Admin",
            user_type="admin",
        )

        buyer = User.objects.create_user(
            phone_number="9876549401",
            password="TestPassword123!",
            full_name="Test Buyer",
            user_type="buyer",
        )

        vendor_user = User.objects.create_user(
            phone_number="9876549402",
            password="TestPassword123!",
            full_name="Test Vendor",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Test Grocery",
            category="supermarket",
            phone_number="9876549402",
            address="Vendor Street",
            town="Test Town",
        )

        partner_user = User.objects.create_user(
            phone_number="9876549403",
            password="TestPassword123!",
            full_name="Test Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=partner_user,
            aadhaar_number="123412341234",
            vehicle_number="AP01AB1234",
        )

        order = Order.objects.create(
            buyer=buyer,
            vendor=vendor,
            delivery_partner=partner_user,
            status="delivered",
            dp_status="delivered",
            total_amount=Decimal("250.00"),
            delivery_address="Buyer Street",
            payment_mode="cod",
            payment_status="paid",
        )

        plan = build_delivery_partner_erasure_plan(partner_user)

        self.assertFalse(
            plan["eligible_for_erasure_review"]
        )

        deletion = create_deletion_request(partner_user)["request"]

        with self.assertRaises(WorkerErasureNotReadyError):
            process_deletion_request(
                deletion.pk,
                approved_by=admin,
            )

        partner_user.refresh_from_db()
        partner.refresh_from_db()
        deletion.refresh_from_db()
        order.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(
            partner_user.phone_number,
            "9876549403",
        )
        self.assertEqual(
            partner.aadhaar_number,
            "123412341234",
        )
        self.assertEqual(deletion.status, "pending")
        self.assertEqual(
            order.delivery_partner_id,
            partner_user.pk,
        )
        self.assertTrue(
            Order.objects.filter(pk=order.pk).exists()
        )
