from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from users.models import User, PasswordResetOTP, AccountDeletionRequest


class DeletionRegistrationSafetyTests(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            phone_number="9876543222",
            password="TestPassword123!",
            full_name="Inactive Deletion Test",
            user_type="buyer",
            is_active=False,
        )

        AccountDeletionRequest.objects.create(
            user=self.user,
            account_type="buyer",
            status="processing",
        )

    def test_processing_deletion_cannot_reactivate_via_registration(self):
        PasswordResetOTP.objects.create(
            user=self.user,
            otp="123456",
        )

        response = self.client.post(
            "/api/users/verify-register-otp/",
            {
                "phone_number": self.user.phone_number,
                "otp": "123456",
                "full_name": "Reactivated User",
                "user_type": "buyer",
            },
            format="json",
        )

        self.user.refresh_from_db()

        self.assertIn(response.status_code, [400, 403])
        self.assertFalse(self.user.is_active)

    def test_processing_deletion_cannot_request_registration_otp(self):
        response = self.client.post(
            "/api/users/send-register-otp/",
            {
                "phone_number": self.user.phone_number,
                "full_name": "Reactivated User",
                "user_type": "buyer",
            },
            format="json",
        )

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.user.is_active)
        self.assertEqual(
            PasswordResetOTP.objects.filter(user=self.user).count(),
            0,
        )

    def test_new_user_can_complete_registration(self):
        new_user = User.objects.create_user(
            phone_number="9876543333",
            password=None,
            full_name="New Registration Test",
            user_type="buyer",
            is_active=False,
        )

        PasswordResetOTP.objects.create(
            user=new_user,
            otp="654321",
        )

        response = self.client.post(
            "/api/users/verify-register-otp/",
            {
                "phone_number": new_user.phone_number,
                "otp": "654321",
                "full_name": "New Registration Test",
                "user_type": "buyer",
            },
            format="json",
        )

        new_user.refresh_from_db()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(new_user.is_active)
        self.assertIn("tokens", response.data)
