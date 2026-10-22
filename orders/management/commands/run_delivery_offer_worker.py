import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from orders.dispatch_service import expire_due_delivery_offers


class Command(BaseCommand):
    help = "Continuously process expired delivery offers."

    def handle(self, *args, **options):
        self.stdout.write(
            "Delivery offer expiration worker started."
        )

        try:
            while True:
                close_old_connections()

                try:
                    expired_count = expire_due_delivery_offers()

                    if expired_count:
                        self.stdout.write(
                            f"Expired {expired_count} delivery offer(s)."
                        )

                except Exception as exc:
                    self.stderr.write(
                        f"Error processing expired delivery offers: {exc}"
                    )

                finally:
                    close_old_connections()

                time.sleep(5)

        except KeyboardInterrupt:
            self.stdout.write(
                "Delivery offer expiration worker stopped."
            )
