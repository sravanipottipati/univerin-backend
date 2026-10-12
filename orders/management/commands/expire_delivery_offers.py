from django.core.management.base import BaseCommand

from orders.dispatch_service import expire_due_delivery_offers


class Command(BaseCommand):
    help = "Expire overdue delivery offers and attempt reassignment."

    def handle(self, *args, **options):
        expired_count = expire_due_delivery_offers()

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {expired_count} expired delivery offer(s)."
            )
        )
