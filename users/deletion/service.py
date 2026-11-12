"""
Central account deletion request service.

This module creates and tracks deletion requests.
It does not deactivate users or delete production data.
"""

import json

from django.db import transaction

from users.models import AccountDeletionRequest, User
from users.deletion.retention import assess_account_deletion


ACTIVE_REQUEST_STATUSES = ["pending", "processing"]


@transaction.atomic
def create_deletion_request(user):
    """
    Create a deletion request for an authenticated user.

    Duplicate pending or processing requests are prevented.
    No account data is deleted or modified.
    """

    # Lock the user row to serialize concurrent deletion requests.
    locked_user = User.objects.select_for_update().get(pk=user.pk)

    if not locked_user.is_active:
        raise ValueError("This account is already deactivated.")

    if locked_user.is_staff or locked_user.is_admin:
        raise ValueError("Administrator accounts cannot use self-service deletion.")

    from users.play_review_otp import is_restricted_review_account

    if is_restricted_review_account(locked_user.phone_number):
        raise ValueError("Reviewer accounts cannot request deletion.")

    # Return an existing active request instead of creating duplicates.
    existing = AccountDeletionRequest.objects.filter(
        user=locked_user,
        status__in=ACTIVE_REQUEST_STATUSES,
    ).first()

    if existing:
        assessment = assess_account_deletion(locked_user)
        return {
            "request": existing,
            "assessment": assessment,
            "created": False,
        }

    # Assess outstanding orders, payments, refunds and settlements.
    assessment = assess_account_deletion(locked_user)

    summary = {
        "can_proceed": assessment.can_proceed,
        "blockers": assessment.blockers,
        "retained_records": assessment.retained_records,
        "personal_data_categories": assessment.personal_data_categories,
        "assessment_only": True,
    }

    deletion_request = AccountDeletionRequest.objects.create(
        user=locked_user,
        account_type=locked_user.user_type,
        status="pending",
        retention_summary=json.dumps(summary),
    )

    return {
        "request": deletion_request,
        "assessment": assessment,
        "created": True,
    }
