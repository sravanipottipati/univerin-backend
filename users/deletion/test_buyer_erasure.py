from unittest.mock import patch

from django.test import TestCase

from users.models import User, Address
from users.deletion.buyer_erasure import (
    erase_buyer_personal_data,
    BuyerErasureNotReadyError,
)


class BuyerErasureTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876545555",
            password="TestPassword123!",
            full_name="Buyer Erasure Test",
            user_type="buyer",
        )

    def test_eligible_buyer_is_anonymized(self):
        erase_buyer_personal_data(self.buyer)

        self.buyer.refresh_from_db()

        self.assertFalse(self.buyer.is_active)
        self.assertTrue(self.buyer.is_deleted)
        self.assertIsNotNone(self.buyer.deleted_at)
        self.assertIsNone(self.buyer.phone_number)
        self.assertEqual(self.buyer.full_name, "Deleted User")
        self.assertFalse(self.buyer.has_usable_password())

    def test_existing_photo_blocks_erasure(self):
        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        with self.assertRaises(BuyerErasureNotReadyError):
            erase_buyer_personal_data(self.buyer)

        self.buyer.refresh_from_db()

        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(
            self.buyer.profile_photo.name,
            "profile_photos/test.jpg",
        )

    def test_photo_reference_preserved_when_erasure_blocked(self):
        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        with patch(
            "django.core.files.storage.default_storage.delete"
        ) as mock_delete:
            with self.assertRaises(BuyerErasureNotReadyError):
                erase_buyer_personal_data(self.buyer)

        mock_delete.assert_not_called()

        self.buyer.refresh_from_db()

        self.assertEqual(
            self.buyer.phone_number,
            "9876545555",
        )
        self.assertEqual(
            self.buyer.profile_photo.name,
            "profile_photos/test.jpg",
        )
        self.assertFalse(self.buyer.is_deleted)

    def test_buyer_with_review_history_cannot_be_erased(self):
        from unittest.mock import patch

        with patch.object(
            type(self.buyer.reviews),
            "exists",
            return_value=True,
        ):
            with self.assertRaises(BuyerErasureNotReadyError):
                erase_buyer_personal_data(self.buyer)

        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.is_deleted)
        self.assertTrue(self.buyer.is_active)

    def test_processor_blocks_buyer_with_profile_photo(self):
        from users.deletion.service import create_deletion_request
        from users.deletion.processor import (
            process_deletion_request,
            DeletionNotImplementedError,
        )

        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        admin = User.objects.create_superuser(
            phone_number="9876549997",
            password="TestPassword123!",
            full_name="Deletion Admin",
            user_type="admin",
        )

        deletion_request = create_deletion_request(
            self.buyer
        )["request"]

        process_deletion_request(
            deletion_request.pk,
            approved_by=admin,
        )

        self.buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

        from users.deletion.cleanup_models import AccountDeletionAsset

        jobs = AccountDeletionAsset.objects.filter(
            deletion_request=deletion_request,
        )

        self.assertEqual(jobs.count(), 1)

        job = jobs.get()
        self.assertEqual(job.owner_type, "user")
        self.assertEqual(job.field_name, "profile_photo")
        self.assertEqual(job.status, "pending")
        self.assertEqual(
            job.storage_reference,
            "profile_photos/test.jpg",
        )
    def test_phone_number_can_be_reused_after_erasure(self):
        original_phone = self.buyer.phone_number

        erase_buyer_personal_data(self.buyer)
        self.buyer.refresh_from_db()

        self.assertIsNone(self.buyer.phone_number)
        self.assertTrue(self.buyer.is_deleted)

        new_buyer = User.objects.create_user(
            phone_number=original_phone,
            password="NewPassword123!",
            full_name="New Buyer",
            user_type="buyer",
        )

        self.assertNotEqual(new_buyer.pk, self.buyer.pk)
        self.assertEqual(new_buyer.phone_number, original_phone)
        self.assertTrue(new_buyer.is_active)

    def test_registration_with_same_phone_after_erasure(self):
        from rest_framework.test import APIClient
        from users.models import PasswordResetOTP

        client = APIClient()
        original_phone = self.buyer.phone_number
        old_user_id = self.buyer.pk

        erase_buyer_personal_data(self.buyer)

        with patch.dict("os.environ", {"TWOFACTOR_API_KEY": ""}):
            response = client.post(
                "/api/users/send-register-otp/",
                {
                    "phone_number": original_phone,
                    "full_name": "New Buyer",
                    "user_type": "buyer",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)

        new_user = User.objects.get(phone_number=original_phone)
        self.assertNotEqual(new_user.pk, old_user_id)

        otp = PasswordResetOTP.objects.filter(
            user=new_user,
            is_used=False,
        ).latest("created_at")

        response = client.post(
            "/api/users/verify-register-otp/",
            {
                "phone_number": original_phone,
                "otp": otp.otp,
                "full_name": "New Buyer",
                "user_type": "buyer",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("tokens", response.data)

        new_user.refresh_from_db()
        self.assertTrue(new_user.is_active)
