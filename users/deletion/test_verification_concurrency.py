import threading
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from users.models import User, AccountDeletionRequest
from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
    AccountDeletionReconciliationAudit,
)
from users.deletion.reconciliation_verification import (
    ReconciliationVerificationError,
    verify_cleanup_asset,
)
from users.deletion.storage_verification import (
    FakeStorageVerifier,
    StorageVerificationResult,
)


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class VerificationConcurrencyTests(TransactionTestCase):

    def setUp(self):
        if connections["default"].vendor != "postgresql":
            self.skipTest("Requires PostgreSQL")

        self.admin = User.objects.create_user(
            phone_number="9876549701",
            password="TestPassword123!",
            full_name="Concurrency Administrator",
            user_type="admin",
            is_staff=True,
            is_admin=True,
        )

        AccountDeletionReconciliationAccess.objects.create(
            administrator=self.admin,
            granted_by=self.admin,
            is_enabled=True,
        )

        user = User.objects.create_user(
            phone_number="9876549702",
            password="TestPassword123!",
            full_name="Concurrency User",
            user_type="buyer",
        )

        request = AccountDeletionRequest.objects.create(
            user=user,
            account_type="buyer",
            status="pending",
        )

        self.attempt_id = uuid.uuid4()

        self.job = AccountDeletionAsset.objects.create(
            deletion_request=request,
            owner_type="user",
            field_name="profile_photo",
            storage_reference="private/original.jpg",
            resource_type="image",
            status="processing",
            attempts=1,
            attempt_id=self.attempt_id,
            lease_expires_at=timezone.now() - timedelta(minutes=5),
        )

    def test_provider_wait_does_not_hold_job_lock(self):
        provider_entered = threading.Event()
        release_provider = threading.Event()
        results = {}
        job_id = self.job.pk
        admin_id = self.admin.pk
        attempt_id = self.attempt_id

        def waiting_verify(
            verifier,
            reference,
            *,
            resource_type,
            storage,
        ):
            provider_entered.set()

            if not release_provider.wait(timeout=10):
                raise RuntimeError("Provider wait timed out")

            return StorageVerificationResult(
                state="absent",
                provider=storage,
                evidence_reference="concurrency-test",
            )

        def worker():
            close_old_connections()
            try:
                admin = User.objects.get(pk=admin_id)
                with patch.object(
                    FakeStorageVerifier,
                    "verify",
                    waiting_verify,
                ):
                    results["verification"] = verify_cleanup_asset(
                        job_id,
                        administrator=admin,
                        attempt_id=attempt_id,
                        verifier=FakeStorageVerifier(state="absent"),
                    )
            except Exception as exc:
                results["error"] = exc
            finally:
                connections["default"].close()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            self.assertTrue(
                provider_entered.wait(timeout=10),
                "Verification did not reach provider",
            )

            # Separate connection, with a short lock timeout.
            with connections["default"].cursor() as cursor:
                cursor.execute("SET lock_timeout = '1500ms'")

            try:
                AccountDeletionAsset.objects.filter(
                    pk=job_id
                ).update(
                    storage_reference="private/changed.jpg"
                )
            finally:
                with connections["default"].cursor() as cursor:
                    cursor.execute("RESET lock_timeout")

        finally:
            release_provider.set()
            thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertIsInstance(
            results.get("error"),
            ReconciliationVerificationError,
        )
        self.assertFalse(
            AccountDeletionReconciliationAudit.objects.exists()
        )
        self.job.refresh_from_db()
        self.assertEqual(
            self.job.storage_reference,
            "private/changed.jpg",
        )
