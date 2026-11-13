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



class RevokedAdministratorAuthorizationTests(TestCase):
    def test_stale_administrator_object_cannot_authorize_deletion(self):
        from users.deletion.service import create_deletion_request
        from users.deletion.processor import process_deletion_request

        administrator = User.objects.create_superuser(
            phone_number="9876549711",
            password="TestPassword123!",
            full_name="Revoked Administrator",
            user_type="admin",
        )

        buyer = User.objects.create_user(
            phone_number="9876549712",
            password="TestPassword123!",
            full_name="Protected Buyer",
            user_type="buyer",
        )

        deletion_request = create_deletion_request(buyer)["request"]

        # Revoke privileges without refreshing the Python object.
        User.objects.filter(pk=administrator.pk).update(
            is_staff=False,
            is_admin=False,
        )

        with self.assertRaises(PermissionError):
            process_deletion_request(
                deletion_request.pk,
                approved_by=administrator,
            )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
