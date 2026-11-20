"""
Automatic account deletion worker.

Dry-run by default. Execution is restricted to the isolated
deletion test database during development.
"""

import logging

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from users.models import AccountDeletionRequest
from users.deletion.processor import DeletionBlockedError
from users.deletion.automatic_orchestrator import (
    process_automatic_deletion_with_assets,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process eligible automatic deletion requests."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Execute eligible deletions in the isolated test database.",
        )

    def handle(self, *args, **options):
        if not options["execute"]:
            self.stdout.write("Automatic deletion worker: DRY RUN")
            call_command(
                "preview_automatic_deletions",
                stdout=self.stdout,
            )
            self.stdout.write(
                "Execution disabled: no accounts were deleted."
            )
            return

        if not settings.ACCOUNT_DELETION_AUTOMATIC_ENABLED:
            raise CommandError(
                "Automatic deletion feature flag is disabled."
            )

        database_name = connection.settings_dict["NAME"]

        is_isolated_test_database = (
            settings.DATABASES["default"].get("TEST", {}).get("NAME")
            == "univerin_deletion_test_20261115"
            and database_name == "univerin_deletion_test_20261115"
        )

        production_execution_allowed = (
            not settings.DEBUG
            and getattr(
                settings,
                "ACCOUNT_DELETION_PRODUCTION_EXECUTION_ALLOWED",
                False,
            )
            and getattr(
                settings,
                "ACCOUNT_DELETION_RAILWAY_ENVIRONMENT",
                "",
            ) == "production"
            and not settings.DATABASES["default"].get("TEST", {}).get("NAME")
            == database_name
            and database_name != "univerin_deletion_test_20261115"
        )

        if not (
            is_isolated_test_database
            or production_execution_allowed
        ):
            raise CommandError(
                "Automatic deletion execution is not authorized "
                "for this database."
            )

        request_ids = list(
            AccountDeletionRequest.objects
            .filter(status="pending")
            .order_by("requested_at")
            .values_list("pk", flat=True)
        )

        completed = 0
        skipped = 0

        for request_id in request_ids:
            try:
                result = process_automatic_deletion_with_assets(request_id)
                if result.status == "completed":
                    completed += 1
                    self.stdout.write(
                        f"COMPLETED: {request_id}"
                    )
                else:
                    skipped += 1
                    self.stdout.write(
                        f"REVIEW: {request_id}"
                    )
            except DeletionBlockedError as exc:
                skipped += 1
                self.stdout.write(
                    f"REVIEW: {request_id} ({exc})"
                )
            except Exception:
                skipped += 1
                logger.exception(
                    "Automatic deletion failed for request %s",
                    request_id,
                )
                self.stderr.write(
                    f"ERROR: {request_id} (see application logs)"
                )

        self.stdout.write(
            f"Summary: {completed} completed, {skipped} skipped."
        )
