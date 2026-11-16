from django.core.management.base import BaseCommand

from users.models import AccountDeletionRequest
from users.play_review_otp import is_restricted_review_account
from users.deletion.preview import preview_account_deletion
from users.deletion.erasure_plan import build_buyer_erasure_plan
from users.deletion.worker_erasure_plan import (
    build_vendor_erasure_plan,
    build_delivery_partner_erasure_plan,
)


class Command(BaseCommand):
    help = "Read-only preview of pending automatic account deletions."

    def handle(self, *args, **options):
        requests = (
            AccountDeletionRequest.objects
            .filter(status="pending")
            .select_related("user")
            .order_by("requested_at")
        )

        counts = {"candidate": 0, "blocked": 0, "review": 0}

        for deletion_request in requests.iterator():
            user = deletion_request.user
            result = "review"
            reason = "Account requires manual review."

            if user is None:
                reason = "Associated user is missing."
            elif (
                user.is_staff
                or user.is_admin
                or is_restricted_review_account(user.phone_number)
                or user.is_deleted
                or not user.is_active
                or deletion_request.account_type != user.user_type
            ):
                reason = "Account is protected, inactive, or inconsistent."
            elif deletion_request.asset_cleanup_jobs.exclude(
                status="completed"
            ).exists():
                reason = (
                    "Unresolved asset cleanup jobs require review."
                )
            else:
                try:
                    preview = preview_account_deletion(user)

                    if not preview["can_proceed"]:
                        result = "blocked"
                        reason = "; ".join(preview["blockers"])
                    else:
                        if user.user_type == "buyer":
                            plan = build_buyer_erasure_plan(user)
                            eligible = plan["eligible_for_erasure_review"]
                            has_assets = bool(user.profile_photo)
                        elif user.user_type == "vendor":
                            plan = build_vendor_erasure_plan(user)
                            eligible = plan["eligible_for_erasure_review"]
                            has_assets = bool(
                                user.profile_photo
                                or user.vendor.fssai_certificate
                                or user.vendor.banner_image
                            )
                        elif user.user_type == "delivery_partner":
                            plan = build_delivery_partner_erasure_plan(user)
                            eligible = plan["eligible_for_erasure_review"]
                            partner = user.delivery_partner
                            has_assets = bool(
                                user.profile_photo
                                or partner.aadhaar_document
                                or partner.pan_document
                                or partner.driving_licence_document
                                or partner.selfie_photo
                            )
                        else:
                            eligible = False
                            has_assets = False

                        if eligible and not has_assets:
                            result = "candidate"
                            reason = "Preliminary candidate; automatic deletion is not authorized."
                        else:
                            reason = (
                                "Historical records, uploaded assets, "
                                "or additional safeguards require review."
                            )

                except Exception as exc:
                    reason = f"Assessment failed: {type(exc).__name__}"

            counts[result] += 1
            self.stdout.write(
                f"{deletion_request.pk} | {user.user_type if user else 'unknown'} "
                f"| {result.upper()} | {reason}"
            )

        self.stdout.write(
            f"\nSummary: {counts['candidate']} candidates, "
            f"{counts['blocked']} blocked, "
            f"{counts['review']} requiring review."
        )
        self.stdout.write("DRY RUN ONLY — no records were modified.")
