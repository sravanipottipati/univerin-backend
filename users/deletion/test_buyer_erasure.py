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
        with patch(
            "users.deletion.buyer_erasure.default_storage.delete"
        ) as mock_delete:
            erase_buyer_personal_data(self.buyer)

        self.buyer.refresh_from_db()

        self.assertFalse(self.buyer.is_active)
        self.assertTrue(self.buyer.is_deleted)
        self.assertIsNotNone(self.buyer.deleted_at)
        self.assertIsNone(self.buyer.phone_number)
        self.assertEqual(self.buyer.full_name, "Deleted User")
        self.assertFalse(self.buyer.has_usable_password())
        mock_delete.assert_not_called()

    def test_existing_photo_is_deleted(self):
        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        with patch(
            "users.deletion.buyer_erasure.default_storage.delete"
        ) as mock_delete:
            erase_buyer_personal_data(self.buyer)

        mock_delete.assert_called_once_with(
            "profile_photos/test.jpg"
        )

    def test_photo_deletion_failure_blocks_erasure(self):
        self.buyer.profile_photo = "profile_photos/test.jpg"
        self.buyer.save(update_fields=["profile_photo"])

        with patch(
            "users.deletion.buyer_erasure.default_storage.delete",
            side_effect=RuntimeError("Cloudinary unavailable"),
        ):
            with self.assertRaises(BuyerErasureNotReadyError):
                erase_buyer_personal_data(self.buyer)

        self.buyer.refresh_from_db()

        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(self.buyer.phone_number, "9876545555")

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
