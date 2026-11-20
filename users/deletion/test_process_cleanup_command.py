from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


class ProcessCleanupCommandTests(TestCase):

    @patch(
        "users.management.commands.process_deletion_cleanup."
        "execute_cleanup_job"
    )
    def test_default_mode_never_executes(self, mock_execute):
        output = StringIO()

        call_command(
            "process_deletion_cleanup",
            stdout=output,
        )

        self.assertIn("DRY RUN ONLY", output.getvalue())
        mock_execute.assert_not_called()

    @override_settings(
        TESTING_ACCOUNT_DELETION_CLEANUP=False
    )
    @patch(
        "users.management.commands.process_deletion_cleanup."
        "execute_cleanup_job"
    )
    def test_execution_requires_isolated_test_authorization(
        self, mock_execute
    ):
        with self.assertRaises(CommandError):
            call_command(
                "process_deletion_cleanup",
                execute_test=True,
                stdout=StringIO(),
            )

        mock_execute.assert_not_called()

    @override_settings(TESTING_ACCOUNT_DELETION_CLEANUP=True)
    def test_simulated_execution_does_not_finalize(self):
        from types import SimpleNamespace

        from unittest.mock import patch

        command = (
            "users.management.commands.process_deletion_cleanup."
        )

        fake_job = SimpleNamespace(pk="simulated-job")

        with patch(
            command + "connection.settings_dict",
            {"NAME": "univerin_deletion_test_20261115"},
        ), patch(
            command + "AccountDeletionAsset.objects.filter"
        ) as mock_filter, patch(
            command + "inspect_cleanup_job",
            return_value={"reference_verified": True},
        ), patch(
            command + "execute_cleanup_job",
            return_value={
                "status": "processing",
                "requires_finalization": True,
            },
        ) as mock_execute:

            mock_filter.return_value.order_by.return_value.values_list.return_value = [
                fake_job.pk,
            ]

            output = StringIO()

            call_command(
                "process_deletion_cleanup",
                execute_test=True,
                stdout=output,
            )

            mock_execute.assert_called_once()
            self.assertIn("PROCESSING:", output.getvalue())
            self.assertIn(
                "No jobs were automatically finalized.",
                output.getvalue(),
            )
