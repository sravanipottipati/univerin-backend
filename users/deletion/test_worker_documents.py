from django.test import TestCase

from users.models import User
from vendors.models import Vendor
from delivery_partner.models import DeliveryPartner
from users.deletion.worker_erasure_plan import (
    build_vendor_erasure_plan,
    build_delivery_partner_erasure_plan,
)
from users.deletion.worker_erasure import (
    erase_vendor_personal_data,
    erase_delivery_partner_personal_data,
    WorkerErasureNotReadyError,
)


class WorkerDocumentProtectionTests(TestCase):

    def test_vendor_certificate_blocks_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549301",
            password="TestPassword123!",
            full_name="Vendor Owner",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=user,
            shop_name="Test Shop",
            category="supermarket",
            phone_number="9876549301",
            address="Test Street",
            town="Test Town",
            fssai_certificate="fssai_certificates/test.jpg",
        )

        plan = build_vendor_erasure_plan(user)
        self.assertFalse(plan["eligible_for_erasure_review"])

        with self.assertRaises(WorkerErasureNotReadyError):
            erase_vendor_personal_data(user)

        user.refresh_from_db()
        vendor.refresh_from_db()

        self.assertFalse(user.is_deleted)
        self.assertTrue(user.is_active)
        self.assertTrue(bool(vendor.fssai_certificate))

    def test_delivery_partner_kyc_document_blocks_erasure(self):
        user = User.objects.create_user(
            phone_number="9876549302",
            password="TestPassword123!",
            full_name="Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=user,
            aadhaar_number="123412341234",
            aadhaar_document="univerin/dp_documents/aadhaar/test",
        )

        plan = build_delivery_partner_erasure_plan(user)
        self.assertFalse(plan["eligible_for_erasure_review"])

        with self.assertRaises(WorkerErasureNotReadyError):
            erase_delivery_partner_personal_data(user)

        user.refresh_from_db()
        partner.refresh_from_db()

        self.assertFalse(user.is_deleted)
        self.assertTrue(user.is_active)
        self.assertEqual(
            partner.aadhaar_number,
            "123412341234",
        )
        self.assertTrue(bool(partner.aadhaar_document))


class WorkerCompletedCleanupProtectionTests(TestCase):
    def setUp(self):
        from users.deletion.processor import process_deletion_request
        from users.deletion.service import create_deletion_request
        from users.deletion.cleanup_models import AccountDeletionAsset

        self.process = process_deletion_request
        self.create_request = create_deletion_request
        self.Asset = AccountDeletionAsset

        self.admin = User.objects.create_superuser(
            phone_number="9876549310",
            password="TestPassword123!",
            full_name="Cleanup Safety Admin",
            user_type="admin",
        )

    def test_vendor_cannot_be_erased_with_certificate_still_attached(self):
        vendor_user = User.objects.create_user(
            phone_number="9876549311",
            password="TestPassword123!",
            full_name="Protected Vendor",
            user_type="vendor",
        )

        vendor = Vendor.objects.create(
            user=vendor_user,
            shop_name="Protected Shop",
            category="supermarket",
            phone_number="9876549311",
            address="Private Street",
            town="Test Town",
            fssai_certificate="fssai_certificates/protected.jpg",
        )

        request = self.create_request(vendor_user)["request"]

        self.process(request.pk, approved_by=self.admin)

        job = self.Asset.objects.get(deletion_request=request)
        job.status = "completed"
        job.save(update_fields=["status"])

        self.process(request.pk, approved_by=self.admin)

        vendor_user.refresh_from_db()
        vendor.refresh_from_db()
        request.refresh_from_db()

        self.assertTrue(vendor_user.is_active)
        self.assertFalse(vendor_user.is_deleted)
        self.assertEqual(request.status, "pending")
        self.assertTrue(bool(vendor.fssai_certificate))

    def test_delivery_partner_cannot_be_erased_with_kyc_still_attached(self):
        partner_user = User.objects.create_user(
            phone_number="9876549312",
            password="TestPassword123!",
            full_name="Protected Delivery Partner",
            user_type="delivery_partner",
        )

        partner = DeliveryPartner.objects.create(
            user=partner_user,
            aadhaar_document="univerin/dp_documents/aadhaar/protected",
        )

        request = self.create_request(partner_user)["request"]

        self.process(request.pk, approved_by=self.admin)

        job = self.Asset.objects.get(deletion_request=request)
        job.status = "completed"
        job.save(update_fields=["status"])

        self.process(request.pk, approved_by=self.admin)

        partner_user.refresh_from_db()
        partner.refresh_from_db()
        request.refresh_from_db()

        self.assertTrue(partner_user.is_active)
        self.assertFalse(partner_user.is_deleted)
        self.assertEqual(request.status, "pending")
        self.assertTrue(bool(partner.aadhaar_document))
