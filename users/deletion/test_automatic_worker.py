from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from users.models import User, AccountDeletionRequest


@override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
class AutomaticDeletionWorkerTests(TestCase):

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_worker_executes_eligible_buyer_deletion(self):
        buyer = User.objects.create_user(
            phone_number="9876548811",
            password="TestPassword123!",
            full_name="Worker Test Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        output = StringIO()

        call_command(
            "process_automatic_deletions",
            execute=True,
            stdout=output,
        )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_deleted)
        self.assertFalse(buyer.is_active)
        self.assertEqual(deletion_request.status, "completed")
        self.assertIn("COMPLETED", output.getvalue())

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_worker_preserves_ineligible_account(self):
        buyer = User.objects.create_user(
            phone_number="9876548812",
            password="TestPassword123!",
            full_name="Ineligible Worker Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="vendor",
            status="pending",
        )

        output = StringIO()
        errors = StringIO()

        call_command(
            "process_automatic_deletions",
            execute=True,
            stdout=output,
            stderr=errors,
        )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
        self.assertIn("ERROR:", errors.getvalue())
        self.assertIn("1 skipped", output.getvalue())

    @override_settings(ACCOUNT_DELETION_AUTOMATIC_ENABLED=True)
    def test_worker_reports_retention_blocker_as_review(self):
        from unittest.mock import patch

        buyer = User.objects.create_user(
            phone_number="9876548813",
            password="TestPassword123!",
            full_name="Blocked Worker Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        output = StringIO()
        errors = StringIO()

        with patch(
            "users.deletion.preview.preview_account_deletion",
            return_value={
                "can_proceed": False,
                "blockers": ["Outstanding orders require resolution."],
            },
        ):
            call_command(
                "process_automatic_deletions",
                execute=True,
                stdout=output,
                stderr=errors,
            )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
        self.assertIn("REVIEW:", output.getvalue())
        self.assertIn("Outstanding orders", output.getvalue())
        self.assertNotIn("ERROR:", errors.getvalue())

    @override_settings(
        ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
        ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED=False,
        DEBUG=False,
    )
    def test_worker_rejects_execution_without_production_authorization(self):
        from unittest.mock import patch
        from django.core.management.base import CommandError

        buyer = User.objects.create_user(
            phone_number="9876548814",
            password="TestPassword123!",
            full_name="Authorization Test Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        with patch(
            "users.management.commands.process_automatic_deletions."
            "connection.settings_dict",
            {"NAME": "production_database"},
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "process_automatic_deletions",
                    execute=True,
                    stdout=StringIO(),
                )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")

    @override_settings(
        ACCOUNT_DELETION_AUTOMATIC_ENABLED=True,
        ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED=True,
        ACCOUNT_DELETION_RAILWAY_ENVIRONMENT="staging",
        DEBUG=False,
    )
    def test_worker_rejects_nonproduction_railway_environment(self):
        from unittest.mock import patch
        from django.core.management.base import CommandError

        buyer = User.objects.create_user(
            phone_number="9876548815",
            password="TestPassword123!",
            full_name="Railway Environment Test Buyer",
            user_type="buyer",
        )

        deletion_request = AccountDeletionRequest.objects.create(
            user=buyer,
            account_type="buyer",
            status="pending",
        )

        with patch(
            "users.management.commands.process_automatic_deletions."
            "connection.settings_dict",
            {"NAME": "production_database"},
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "process_automatic_deletions",
                    execute=True,
                    stdout=StringIO(),
                )

        buyer.refresh_from_db()
        deletion_request.refresh_from_db()

        self.assertTrue(buyer.is_active)
        self.assertFalse(buyer.is_deleted)
        self.assertEqual(deletion_request.status, "pending")
