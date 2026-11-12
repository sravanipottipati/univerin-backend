from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_reconciliation import (
    CleanupReconciliationError,
    inspect_cleanup_for_reconciliation,
)


class CleanupReconciliationTests(TestCase):

    def setUp(self):
        self.admin = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=True,
        )

        self.non_admin = SimpleNamespace(
            is_authenticated=True,
            is_active=True,
            is_staff=False,
        )

    def test_unauthorized_access_rejected(self):
        for actor in (None, self.non_admin):
            with self.subTest(actor=actor):
                with self.assertRaises(CleanupReconciliationError):
                    inspect_cleanup_for_reconciliation(
                        "00000000-0000-0000-0000-000000000000",
                        admin=actor,
                    )

    def test_inactive_admin_rejected(self):
        inactive_admin = SimpleNamespace(
            is_authenticated=True,
            is_active=False,
            is_staff=True,
        )

        with self.assertRaises(CleanupReconciliationError):
            inspect_cleanup_for_reconciliation(
                "00000000-0000-0000-0000-000000000000",
                admin=inactive_admin,
            )

    def test_missing_job_rejected(self):
        with self.assertRaises(CleanupReconciliationError):
            inspect_cleanup_for_reconciliation(
                "00000000-0000-0000-0000-000000000000",
                admin=self.admin,
            )

    def test_processing_job_without_lease_requires_reconciliation(self):
        from users.models import User, AccountDeletionRequest

        user = User.objects.create_user(
            phone_number="9876549841",
            password="TestPassword123!",
            user_type="buyer",
        )

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        job = AccountDeletionAsset.objects.create(
            deletion_request=request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/test-image.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            lease_expires_at=None,
        )

        result = inspect_cleanup_for_reconciliation(
            job.pk,
            admin=self.admin,
        )

        self.assertTrue(result["requires_reconciliation"])
        self.assertFalse(result["automatic_retry_allowed"])
        self.assertFalse(result["storage_reference_exposed"])
        self.assertNotIn("storage_reference", result)

        job.refresh_from_db()
        self.assertEqual(job.status, "processing")
        self.assertEqual(
            job.storage_reference,
            "private/test-image.jpg",
        )

    def test_expired_processing_job_requires_reconciliation(self):
        from users.models import User, AccountDeletionRequest

        user = User.objects.create_user(
            phone_number="9876549842",
            password="TestPassword123!",
            user_type="buyer",
        )

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        job = AccountDeletionAsset.objects.create(
            deletion_request=request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/expired-image.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

        result = inspect_cleanup_for_reconciliation(
            job.pk,
            admin=self.admin,
        )

        self.assertTrue(result["lease_expired"])
        self.assertTrue(result["requires_reconciliation"])
        self.assertFalse(result["automatic_retry_allowed"])

    def test_healthy_processing_job_does_not_require_reconciliation(self):
        from users.models import User, AccountDeletionRequest

        user = User.objects.create_user(
            phone_number="9876549843",
            password="TestPassword123!",
            user_type="buyer",
        )

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        job = AccountDeletionAsset.objects.create(
            deletion_request=request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/healthy-image.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            lease_expires_at=timezone.now() + timedelta(minutes=10),
        )

        result = inspect_cleanup_for_reconciliation(
            job.pk,
            admin=self.admin,
        )

        self.assertFalse(result["lease_expired"])
        self.assertFalse(result["outcome_uncertain"])
        self.assertFalse(result["requires_reconciliation"])

    def test_uncertain_outcome_requires_reconciliation(self):
        from users.models import User, AccountDeletionRequest

        user = User.objects.create_user(
            phone_number="9876549844",
            password="TestPassword123!",
            user_type="buyer",
        )

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        job = AccountDeletionAsset.objects.create(
            deletion_request=request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/uncertain-image.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            lease_expires_at=timezone.now() + timedelta(minutes=10),
            last_error="Storage outcome uncertain",
        )

        result = inspect_cleanup_for_reconciliation(
            job.pk,
            admin=self.admin,
        )

        self.assertTrue(result["outcome_uncertain"])
        self.assertTrue(result["requires_reconciliation"])
        self.assertFalse(result["automatic_retry_allowed"])
