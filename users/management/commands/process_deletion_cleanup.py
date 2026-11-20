"""
Restricted account deletion cleanup command.

Dry-run by default. No production storage execution.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from users.deletion.cleanup_models import AccountDeletionAsset
from users.deletion.cleanup_worker import inspect_cleanup_job
from users.deletion.storage_adapter import FakeStorageAdapter
from users.deletion.cleanup_executor import execute_cleanup_job


class Command(BaseCommand):
    help = "Process account deletion cleanup in isolated tests only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute-test",
            action="store_true",
            help="Execute with fake storage in the isolated test DB.",
        )

    def handle(self, *args, **options):
        if not options["execute_test"]:
            self.stdout.write(
                "DRY RUN ONLY. Use preview_deletion_cleanup "
                "to inspect queued jobs."
            )
            return

        database_name = connection.settings_dict["NAME"]

        if not (
            getattr(
                settings, "TESTING_ACCOUNT_DELETION_CLEANUP", False
            )
            and database_name == "univerin_deletion_test_20261115"
            and settings.DATABASES["default"].get(
                "TEST", {}
            ).get("NAME") == database_name
        ):
            raise CommandError(
                "Test cleanup execution requires the isolated test database."
            )

        jobs = list(
            AccountDeletionAsset.objects.filter(
                status__in=["pending", "failed"]
            ).order_by("created_at").values_list("pk", flat=True)
        )

        for job_id in jobs:
            try:
                inspect_cleanup_job(job_id)
                result = execute_cleanup_job(
                    job_id,
                    adapter=FakeStorageAdapter(),
                )
                self.stdout.write(
                    f"PROCESSING: {job_id} — {result['status']}; "
                    "administrator reconciliation required"
                )
            except Exception as exc:
                self.stderr.write(
                    f"BLOCKED: {job_id} — {exc}"
                )

        self.stdout.write(
            "Test cleanup execution complete. "
            "No jobs were automatically finalized."
        )
