"""
Retention and outstanding-obligation checks for account deletion.

This module identifies records requiring review. It does not delete,
modify, or anonymize any production data.
"""

from dataclasses import dataclass, field


@dataclass
class RetentionAssessment:
    can_proceed: bool
    account_type: str
    blockers: list = field(default_factory=list)
    retained_records: list = field(default_factory=list)
    personal_data_categories: list = field(default_factory=list)


def assess_account_deletion(user):
    """
    Inspect an account and identify outstanding obligations.

    Actual deletion decisions must follow an approved retention policy.
    """

    assessment = RetentionAssessment(
        can_proceed=True,
        account_type=user.user_type,
    )

    # Historical financial and transaction records.
    assessment.retained_records.extend([
        "Historical orders requiring retention review",
        "Issued invoices and credit notes",
        "Razorpay checkout and payment records",
        "Wallet transactions and settlement records",
    ])

    assessment.personal_data_categories.extend([
        "Account contact information",
        "Saved addresses",
        "Profile photo",
        "Push notification token",
    ])

    if user.user_type == "buyer":
        # Unconfirmed checkouts may still be needed for payment
        # verification or order creation. Never erase them prematurely.
        pending_checkouts = user.razorpay_checkouts.filter(
            status="created"
        )

        if pending_checkouts.exists():
            assessment.blockers.append(
                "Unconfirmed Razorpay checkouts require resolution."
            )

        pending_orders = user.orders.exclude(
            status__in=["delivered", "cancelled", "rejected"]
        )

        if pending_orders.exists():
            assessment.blockers.append(
                "Outstanding orders require resolution."
            )

        # ReturnRequest currently has no resolution status.
        # Require review before allowing account erasure.
        from orders.models import ReturnRequest

        pending_returns = ReturnRequest.objects.filter(
            buyer=user
        )

        if pending_returns.exists():
            assessment.blockers.append(
                "Return requests require resolution before account deletion."
            )

        pending_refunds = user.refunds.filter(
            status__in=["requested", "approved"]
        )

        if pending_refunds.exists():
            assessment.blockers.append(
                "Outstanding refund requests require resolution."
            )

        unpaid_delivered_orders = user.orders.filter(
            status="delivered",
            payment_status="pending",
        )

        if unpaid_delivered_orders.exists():
            assessment.blockers.append(
                "Delivered orders with outstanding payments require resolution."
            )

    elif user.user_type == "vendor":
        try:
            vendor = user.vendor
        except Exception:
            assessment.blockers.append(
                "Vendor profile could not be verified."
            )
        else:
            active_orders = vendor.orders.exclude(
                status__in=["delivered", "cancelled", "rejected"]
            )

            if active_orders.exists():
                assessment.blockers.append(
                    "Outstanding vendor orders require resolution."
                )

            pending_platform_fees = vendor.transactions.filter(
                transaction_type="debit",
                status="pending",
            )

            if pending_platform_fees.exists():
                assessment.blockers.append(
                    "Outstanding platform fees require settlement."
                )

            assessment.retained_records.extend([
                "Vendor business and tax records",
                "Vendor wallet and settlement history",
            ])

            assessment.personal_data_categories.extend([
                "Vendor banking information",
                "Vendor KYC information",
                "Vendor uploaded documents",
            ])

    elif user.user_type == "delivery_partner":
        active_deliveries = user.deliveries.filter(
            dp_status__in=[
                "accepted",
                "arrived_at_shop",
                "picked_up",
                "arrived_at_buyer",
            ]
        )

        if active_deliveries.exists():
            assessment.blockers.append(
                "Active deliveries must be completed or reassigned."
            )

        pending_delivery_payments = user.deliveries.filter(
            status="delivered",
            payment_mode="cod",
            payment_status="pending",
        )

        if pending_delivery_payments.exists():
            assessment.blockers.append(
                "Outstanding COD collections require resolution."
            )

        assessment.personal_data_categories.extend([
            "Delivery partner KYC documents",
            "Vehicle and licence information",
            "Current location information",
        ])

    else:
        assessment.blockers.append(
            "Unsupported account type for self-service deletion."
        )

    assessment.can_proceed = not assessment.blockers

    return assessment
