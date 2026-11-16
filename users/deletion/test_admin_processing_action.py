from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, TestCase

from users.admin import AccountDeletionRequestAdmin
from users.models import AccountDeletionRequest, User


class AdminProcessingActionTests(TestCase):

    def test_admin_action_processes_eligible_buyer(self):
        administrator = User.objects.create_user(
            phone_number="9876549681",
            password="TestPassword123!",
            full_name="Deletion Admin",
            user_type="buyer",
        )
        administrator.is_staff = True
        administrator.is_admin = True
        administrator.save(update_fields=["is_staff", "is_admin"])

        buyer = User.objects.create_user(
            phone_number="9876549682",
            password="TestPassword123!",
            full_name="Deletion Test Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        request = RequestFactory().post("/admin/users/accountdeletionrequest/")
        request.user = administrator

        model_admin = AccountDeletionRequestAdmin(
            AccountDeletionRequest,
            admin.site,
        )

        with patch.object(model_admin, "message_user"):
            model_admin.process_selected_deletion_requests(
                request,
                AccountDeletionRequest.objects.filter(
                    pk=deletion_request.pk
                ),
            )

        deletion_request.refresh_from_db()
        buyer.refresh_from_db()

        self.assertEqual(deletion_request.status, "completed")
        self.assertTrue(buyer.is_deleted)
        self.assertFalse(buyer.is_active)

    def test_unauthorized_user_cannot_process_request(self):
        buyer = User.objects.create_user(
            phone_number="9876549683",
            password="TestPassword123!",
            full_name="Unauthorized User",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        request = RequestFactory().post(
            "/admin/users/accountdeletionrequest/"
        )
        request.user = buyer

        model_admin = AccountDeletionRequestAdmin(
            AccountDeletionRequest,
            admin.site,
        )

        with patch.object(model_admin, "message_user"):
            model_admin.process_selected_deletion_requests(
                request,
                AccountDeletionRequest.objects.filter(
                    pk=deletion_request.pk
                ),
            )

        deletion_request.refresh_from_db()
        buyer.refresh_from_db()

        self.assertEqual(deletion_request.status, "pending")
        self.assertFalse(buyer.is_deleted)
        self.assertTrue(buyer.is_active)

    def test_uploaded_asset_prevents_immediate_deletion(self):
        administrator = User.objects.create_user(
            phone_number="9876549684",
            password="TestPassword123!",
            full_name="Asset Cleanup Admin",
            user_type="buyer",
        )
        administrator.is_staff = True
        administrator.is_admin = True
        administrator.save(update_fields=["is_staff", "is_admin"])

        buyer = User.objects.create_user(
            phone_number="9876549685",
            password="TestPassword123!",
            full_name="Buyer With Photo",
            user_type="buyer",
        )
        buyer.profile_photo = "profile_photos/pending-cleanup.jpg"
        buyer.save(update_fields=["profile_photo"])

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        request = RequestFactory().post(
            "/admin/users/accountdeletionrequest/"
        )
        request.user = administrator

        model_admin = AccountDeletionRequestAdmin(
            AccountDeletionRequest,
            admin.site,
        )

        with patch.object(model_admin, "message_user"):
            model_admin.process_selected_deletion_requests(
                request,
                AccountDeletionRequest.objects.filter(
                    pk=deletion_request.pk
                ),
            )

        deletion_request.refresh_from_db()
        buyer.refresh_from_db()

        self.assertEqual(deletion_request.status, "pending")
        self.assertFalse(buyer.is_deleted)
        self.assertTrue(buyer.is_active)
        self.assertTrue(bool(buyer.profile_photo))
        self.assertTrue(
            deletion_request.asset_cleanup_jobs.exists()
        )
