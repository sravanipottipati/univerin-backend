from django.test import TestCase

from users.models import User, AccountDeletionRequest
from users.deletion.service import create_deletion_request


class AccountDeletionServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543210",
            password="TestPassword123!",
            full_name="Deletion Test Buyer",
            user_type="buyer",
        )

    def test_buyer_can_submit_deletion_request(self):
        result = create_deletion_request(self.user)

        self.assertTrue(result["created"])
        self.assertEqual(result["request"].status, "pending")
        self.assertEqual(AccountDeletionRequest.objects.count(), 1)

    def test_duplicate_request_is_prevented(self):
        first = create_deletion_request(self.user)
        second = create_deletion_request(self.user)

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(
            first["request"].id,
            second["request"].id,
        )
        self.assertEqual(AccountDeletionRequest.objects.count(), 1)

    def test_account_remains_active_after_request(self):
        create_deletion_request(self.user)

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.full_name, "Deletion Test Buyer")

    def test_reviewer_account_is_rejected(self):
        reviewer = User.objects.create_user(
            phone_number="9999999991",
            password="TestPassword123!",
            full_name="Reviewer Account",
            user_type="buyer",
        )

        with self.assertRaisesMessage(
            ValueError,
            "Reviewer accounts cannot request deletion.",
        ):
            create_deletion_request(reviewer)

        self.assertEqual(AccountDeletionRequest.objects.count(), 0)
        self.assertTrue(reviewer.is_active)


from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from django.urls import reverse


class AccountDeletionAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="9876543211",
            password="TestPassword123!",
            full_name="Deletion API Test Buyer",
            user_type="buyer",
        )

        self.request_url = reverse("delete-account-request")
        self.status_url = reverse("deletion-status")

        token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    def test_authenticated_user_can_submit_request(self):
        response = self.client.post(self.request_url, {}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["created"])
        self.assertEqual(response.data["request_status"], "pending")
        self.assertEqual(AccountDeletionRequest.objects.count(), 1)

    def test_duplicate_request_returns_existing_request(self):
        first = self.client.post(self.request_url, {}, format="json")
        second = self.client.post(self.request_url, {}, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(AccountDeletionRequest.objects.count(), 1)

    def test_deletion_status_returns_latest_request(self):
        self.client.post(self.request_url, {}, format="json")

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 200)

    def test_account_remains_active_after_api_request(self):
        self.client.post(self.request_url, {}, format="json")

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.full_name, "Deletion API Test Buyer")

    def test_unauthenticated_user_cannot_submit_request(self):
        self.client.credentials()

        response = self.client.post(self.request_url, {}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(AccountDeletionRequest.objects.count(), 0)

    def test_unauthenticated_user_cannot_check_status(self):
        self.client.credentials()

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 401)
