from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from users.deletion.cleanup_models import AccountDeletionAsset


class CleanupPreviewCommandTests(TestCase):

    def test_empty_queue(self):
        output = StringIO()

        call_command("preview_deletion_cleanup", stdout=output)

        self.assertIn("0 validated, 0 blocked", output.getvalue())

    def test_valid_and_blocked_jobs_are_read_only(self):
        with patch(
            "users.management.commands.preview_deletion_cleanup."
            "AccountDeletionAsset.objects.filter"
        ) as mock_filter, patch(
            "users.management.commands.preview_deletion_cleanup."
            "inspect_cleanup_job"
        ) as mock_inspect, patch(
            "users.deletion.cleanup_executor.execute_cleanup_job"
        ) as mock_execute:

            from types import SimpleNamespace
            from users.deletion.cleanup_worker import (
                AssetCleanupBlockedError,
            )

            jobs = [
                SimpleNamespace(pk="valid-job"),
                SimpleNamespace(pk="blocked-job"),
            ]

            mock_filter.return_value.order_by.return_value.iterator.return_value = (
                iter(jobs)
            )

            mock_inspect.side_effect = [
                {"reference_verified": True},
                AssetCleanupBlockedError("Asset reference changed."),
            ]

            output = StringIO()
            call_command(
                "preview_deletion_cleanup",
                stdout=output,
            )

            self.assertIn("1 validated, 1 blocked", output.getvalue())
            self.assertIn("Asset reference changed.", output.getvalue())
            self.assertEqual(mock_inspect.call_count, 2)
            mock_execute.assert_not_called()
