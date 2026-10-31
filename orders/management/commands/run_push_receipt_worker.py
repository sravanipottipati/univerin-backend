"""Background worker for verifying Expo push receipts."""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from orders.push_receipt_service import verify_push_receipts

logger = logging.getLogger(__name__)

RECEIPT_CHECK_INTERVAL_SECONDS = 60


class Command(BaseCommand):
    help = "Continuously verify Expo push notification receipts."

    def handle(self, *args, **options):
        self.stdout.write(
            "UNIVERIN Expo push receipt worker started."
        )

        try:
            while True:
                close_old_connections()

                try:
                    processed = verify_push_receipts()

                    if processed:
                        logger.info(
                            "Verified %s Expo push receipts",
                            processed,
                        )

                except Exception:
                    logger.exception(
                        "Unexpected Expo receipt worker error"
                    )

                finally:
                    close_old_connections()

                time.sleep(RECEIPT_CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            self.stdout.write(
                "UNIVERIN Expo push receipt worker stopped."
            )
