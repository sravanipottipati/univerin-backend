from django.test import TestCase
from rest_framework_simplejwt.tokens import AccessToken
from users.authentication import ActiveAccountJWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.models import User


class DeletedAccountAuthenticationTests(TestCase):

    def test_deleted_account_cannot_authenticate_with_jwt(self):
        user = User.objects.create_user(
            phone_number="9876546666",
            password="TestPassword123!",
            full_name="Deleted Test User",
            user_type="buyer",
            is_active=True,
            is_deleted=True,
        )

        token = AccessToken.for_user(user)

        auth = ActiveAccountJWTAuthentication()

        with self.assertRaises(AuthenticationFailed):
            auth.get_user(token)

    def test_deactivated_account_cannot_authenticate_with_jwt(self):
        user = User.objects.create_user(
            phone_number="9876546667",
            password="TestPassword123!",
            full_name="Deactivated Test User",
            user_type="buyer",
            is_active=False,
            is_deleted=False,
        )

        token = AccessToken.for_user(user)
        auth = ActiveAccountJWTAuthentication()

        with self.assertRaises(AuthenticationFailed):
            auth.get_user(token)
