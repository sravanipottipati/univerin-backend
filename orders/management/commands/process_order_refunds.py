from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from datetime import timedelta
from django.utils import timezone

from orders.models import Refund
from orders.refund_service import (
    RefundError,
    process_reserved_refund,
    reconcile_order_refund,
)


class Command(BaseCommand):
    help = "Process and reconcile Razorpay refunds. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Execute refund processing instead of dry-run.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum refunds to inspect per run.",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        limit = options["limit"]

        if limit < 1 or limit > 100:
            raise CommandError("--limit must be between 1 and 100.")

        if execute and not getattr(
            settings, "RAZORPAY_AUTO_REFUNDS_ENABLED", False
        ):
            raise CommandError(
                "Automatic Razorpay refunds are disabled."
            )

        refunds = list(
            Refund.objects.filter(
                processing_state__in=["reserved", "initiated"]
            )
            .order_by("requested_at")[:limit]
        )

        processed = 0
        reconciled = 0
        errors = 0

        for refund in refunds:
            if not execute:
                self.stdout.write(
                    f"DRY RUN: refund={refund.pk} "
                    f"state={refund.processing_state} "
                    f"amount_paise={refund.amount_paise}"
                )
                continue

            try:
                if refund.processing_state == "reserved":
                    process_reserved_refund(refund.pk)
                    processed += 1

                elif (
                    refund.processing_state == "initiated"
                    and refund.razorpay_refund_id
                ):
                    reconcile_order_refund(refund.pk)
                    reconciled += 1

                else:
                    cutoff = timezone.now() - timedelta(minutes=15)
                    if (
                        refund.processing_state == "initiated"
                        and not refund.razorpay_refund_id
                        and refund.initiated_at
                        and refund.initiated_at <= cutoff
                    ):
                        updated = Refund.objects.filter(
                            pk=refund.pk,
                            processing_state="initiated",
                            razorpay_refund_id__isnull=True,
                            initiated_at__lte=cutoff,
                        ).update(
                            processing_state="requires_review",
                            failure_reason=(
                                "Interrupted refund without provider ID. "
                                "Check Razorpay refund history before "
                                "taking any further action."
                            ),
                            updated_at=timezone.now(),
                        )
                        if updated:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"REQUIRES REVIEW: refund={refund.pk}"
                                )
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"SKIPPED: refund={refund.pk}; "
                                "awaiting reconciliation."
                            )
                        )

            except RefundError as exc:
                errors += 1
                self.stderr.write(
                    f"REFUND ERROR: refund={refund.pk}: {exc}"
                )

        self.stdout.write(
            f"Refund worker complete: "
            f"inspected={len(refunds)}, "
            f"initiated={processed}, "
            f"reconciled={reconciled}, "
            f"errors={errors}, "
            f"dry_run={not execute}"
        )
