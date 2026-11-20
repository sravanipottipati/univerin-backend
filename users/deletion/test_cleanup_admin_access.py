from django.contrib import admin
from django.test import RequestFactory, TestCase

from users.models import User
from users.deletion.cleanup_models import AccountDeletionAsset
from users.admin import AccountDeletionAssetAdmin


class CleanupAdminAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.model_admin = AccountDeletionAssetAdmin(
            AccountDeletionAsset,
            admin.site,
        )

    def make_request(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_regular_user_cannot_access_cleanup_admin(self):
        user = User.objects.create(
            phone_number="9000000101",
            user_type="buyer",
            is_active=True,
            is_staff=False,
            is_admin=False,
        )
        request = self.make_request(user)

        self.assertFalse(self.model_admin.has_view_permission(request))
        self.assertFalse(self.model_admin.has_module_permission(request))

    def test_admin_can_view_cleanup_jobs(self):
        user = User.objects.create(
            phone_number="9000000102",
            user_type="admin",
            is_active=True,
            is_staff=True,
            is_admin=True,
        )
        request = self.make_request(user)

        self.assertTrue(self.model_admin.has_view_permission(request))
        self.assertTrue(self.model_admin.has_module_permission(request))

    def test_admin_cannot_modify_cleanup_jobs(self):
        user = User.objects.create(
            phone_number="9000000103",
            user_type="admin",
            is_active=True,
            is_staff=True,
            is_admin=True,
        )
        request = self.make_request(user)

        self.assertFalse(self.model_admin.has_add_permission(request))
        self.assertFalse(self.model_admin.has_change_permission(request))
        self.assertFalse(self.model_admin.has_delete_permission(request))

    def test_inactive_admin_cannot_view_cleanup_jobs(self):
        user = User.objects.create(
            phone_number="9000000104",
            user_type="admin",
            is_active=False,
            is_staff=True,
            is_admin=True,
        )
        request = self.make_request(user)

        self.assertFalse(self.model_admin.has_view_permission(request))
