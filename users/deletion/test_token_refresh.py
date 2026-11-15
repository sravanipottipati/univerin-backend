from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User, AccountDeletionRequest
from users.token_refresh import ActiveAccountTokenRefreshSerializer


class TokenRefreshSecurityTests(TestCase):

    def create_user(self, phone, is_deleted=False):
        return User.objects.create_user(
            phone_number=phone,
            password="TestPassword123!",
            full_name="Refresh Test User",
            user_type="buyer",
            is_active=True,
            is_deleted=is_deleted,
        )

    def refresh_serializer(self, user):
        token = RefreshToken.for_user(user)
        return ActiveAccountTokenRefreshSerializer(
            data={"refresh": str(token)}
        )

    def test_active_user_can_refresh_token(self):
        user = self.create_user("9876546101")
        serializer = self.refresh_serializer(user)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIn("access", serializer.validated_data)

    def test_deleted_user_cannot_refresh_token(self):
        user = self.create_user(
            "9876546102",
            is_deleted=True,
        )
        serializer = self.refresh_serializer(user)

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_pending_deletion_user_cannot_refresh_token(self):
        user = self.create_user("9876546103")

        AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        serializer = self.refresh_serializer(user)

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_nonexistent_user_cannot_refresh_token(self):
        user = self.create_user("9876546104")
        token = RefreshToken.for_user(user)

        user.delete()

        serializer = ActiveAccountTokenRefreshSerializer(
            data={"refresh": str(token)}
        )

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)


from rest_framework.test import APIClient


class TokenRefreshEndpointTests(TestCase):

    endpoint = "/api/users/token/refresh/"

    def create_user(self, phone, is_deleted=False):
        return User.objects.create_user(
            phone_number=phone,
            password="TestPassword123!",
            full_name="Endpoint Test User",
            user_type="buyer",
            is_active=True,
            is_deleted=is_deleted,
        )

    def post_refresh(self, user):
        token = RefreshToken.for_user(user)
        client = APIClient()
        return client.post(
            self.endpoint,
            {"refresh": str(token)},
            format="json",
        )

    def test_active_user_receives_new_access_token(self):
        user = self.create_user("9876546201")
        response = self.post_refresh(user)

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_deleted_user_receives_401(self):
        user = self.create_user(
            "9876546202",
            is_deleted=True,
        )
        response = self.post_refresh(user)

        self.assertEqual(response.status_code, 401)

    def test_pending_deletion_user_receives_401(self):
        user = self.create_user("9876546203")

        AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        response = self.post_refresh(user)

        self.assertEqual(response.status_code, 401)

    def test_nonexistent_user_receives_401(self):
        user = self.create_user("9876546204")
        token = RefreshToken.for_user(user)
        user.delete()

        response = APIClient().post(
            self.endpoint,
            {"refresh": str(token)},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
