from django.contrib import admin
from django.test import RequestFactory, TestCase

from users.models import User
from users.admin import AccountDeletionReconciliationAuditAdmin
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAudit,
)


class ReconciliationAdminAccessTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.model_admin = AccountDeletionReconciliationAuditAdmin(
            AccountDeletionReconciliationAudit,
            admin.site,
        )

    def make_request(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def make_user(self, phone, *, admin_role=False, active=True):
        return User.objects.create(
            phone_number=phone,
            user_type="admin" if admin_role else "buyer",
            is_active=active,
            is_staff=admin_role,
            is_admin=admin_role,
        )

    def test_buyer_cannot_view_audits(self):
        request = self.make_request(self.make_user("9000000201"))
        self.assertFalse(self.model_admin.has_view_permission(request))

    def test_admin_can_view_audits(self):
        request = self.make_request(
            self.make_user("9000000202", admin_role=True)
        )
        self.assertTrue(self.model_admin.has_view_permission(request))

    def test_inactive_admin_cannot_view_audits(self):
        request = self.make_request(
            self.make_user("9000000203", admin_role=True, active=False)
        )
        self.assertFalse(self.model_admin.has_view_permission(request))

    def test_admin_cannot_modify_audits(self):
        request = self.make_request(
            self.make_user("9000000204", admin_role=True)
        )
        self.assertFalse(self.model_admin.has_add_permission(request))
        self.assertFalse(self.model_admin.has_change_permission(request))
        self.assertFalse(self.model_admin.has_delete_permission(request))
