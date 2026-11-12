from django.test import TestCase

from users.models import User
from users.deletion.service import create_deletion_request
from users.deletion.processor import (
    process_deletion_request,
    DeletionNotImplementedError,
)


class AdminDeletionAuthorizationTests(TestCase):

    def setUp(self):
        self.buyer = User.objects.create_user(
            phone_number="9876549901",
            password="TestPassword123!",
            full_name="Buyer Test",
            user_type="buyer",
        )

        self.admin = User.objects.create_superuser(
            phone_number="9876549902",
            password="TestPassword123!",
            full_name="Admin Test",
            user_type="admin",
        )

        self.deletion_request = create_deletion_request(
            self.buyer
        )["request"]

    def test_buyer_cannot_authorize_deletion(self):
        with self.assertRaises(PermissionError):
            process_deletion_request(
                self.deletion_request.id,
                approved_by=self.buyer,
            )

        self.buyer.refresh_from_db()
        self.deletion_request.refresh_from_db()

        self.assertTrue(self.buyer.is_active)
        self.assertFalse(self.buyer.is_deleted)
        self.assertEqual(
            self.deletion_request.status,
            "pending",
        )

    def test_admin_can_process_eligible_buyer(self):
        process_deletion_request(
            self.deletion_request.id,
            approved_by=self.admin,
        )

        self.buyer.refresh_from_db()
        self.deletion_request.refresh_from_db()

        self.assertFalse(self.buyer.is_active)
        self.assertTrue(self.buyer.is_deleted)
        self.assertEqual(
            self.deletion_request.status,
            "completed",
        )
        self.assertIsNotNone(self.deletion_request.completed_at)

