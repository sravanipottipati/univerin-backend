"""
Restricted administrative reconciliation for account deletion assets.

Verification is read-only. Confirmation and finalization require
matching, previously recorded evidence. No storage deletion occurs here.
"""

import uuid

from django.core.management.base import BaseCommand, CommandError

from users.models import User
from users.deletion.reconciliation_models import (
    AccountDeletionReconciliationAccess,
)
from users.deletion.reconciliation_verification import (
    verify_cleanup_asset,
)
from users.deletion.reconciliation_service import (
    confirm_cleanup_deletion,
)
from users.deletion.cleanup_finalizer import (
    finalize_verified_cleanup_job,
)


class Command(BaseCommand):
    help = "Verify, confirm, or finalize an account deletion cleanup job."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["verify", "confirm", "finalize"],
        )
        parser.add_argument("--job-id", required=True)
        parser.add_argument("--attempt-id", required=True)
        parser.add_argument("--admin-id", required=True)
        parser.add_argument("--verification-id")
        parser.add_argument("--confirmation-id")
        parser.add_argument("--explanation")

    def handle(self, *args, **options):
        from django.conf import settings
        from django.db import connection

        database_name = connection.settings_dict["NAME"]

        if not (
            getattr(settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False)
            and database_name == "univerin_deletion_test_20261115"
            and settings.DATABASES["default"].get(
                "TEST", {}
            ).get("NAME") == database_name
        ):
            raise CommandError(
                "Reconciliation command is restricted to "
                "the isolated test database."
            )

        action = options["action"]

        try:
            job_id = uuid.UUID(options["job_id"])
            attempt_id = uuid.UUID(options["attempt_id"])
            admin_id = uuid.UUID(options["admin_id"])
        except (ValueError, TypeError) as exc:
            raise CommandError("Invalid job, attempt, or administrator ID.") from exc

        administrator = User.objects.filter(
            pk=admin_id,
            is_active=True,
            is_staff=True,
            is_admin=True,
            is_deleted=False,
        ).first()

        if administrator is None:
            raise CommandError("Active deletion administrator required.")

        if not AccountDeletionReconciliationAccess.objects.filter(
            administrator=administrator,
            is_enabled=True,
        ).exists():
            raise CommandError(
                "Administrator lacks explicit reconciliation authorization."
            )

        try:
            if action == "verify":
                result = verify_cleanup_asset(
                    job_id,
                    administrator=administrator,
                    attempt_id=attempt_id,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Verification state: {result['verification_state']}; "
                        f"audit ID: {result['audit_id']}"
                    )
                )

            elif action == "confirm":
                if not options["verification_id"]:
                    raise CommandError("--verification-id is required.")
                if not options["explanation"]:
                    raise CommandError("--explanation is required.")

                verification_id = uuid.UUID(options["verification_id"])

                audit = confirm_cleanup_deletion(
                    job_id,
                    administrator=administrator,
                    attempt_id=attempt_id,
                    verification_audit_id=verification_id,
                    explanation=options["explanation"],
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Confirmation recorded; audit ID: {audit.pk}"
                    )
                )

            elif action == "finalize":
                if not options["confirmation_id"]:
                    raise CommandError("--confirmation-id is required.")

                confirmation_id = uuid.UUID(options["confirmation_id"])

                job = finalize_verified_cleanup_job(
                    job_id,
                    administrator=administrator,
                    attempt_id=attempt_id,
                    confirmation_audit_id=confirmation_id,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Cleanup job {job.pk}: {job.status}"
                    )
                )

        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                f"Reconciliation blocked: {exc}"
            ) from exc
