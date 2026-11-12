"""
Buyer personal-data erasure operations.

Safety status:
- No database records are modified.
- No files are deleted.
- Actual erasure is not implemented.
"""


class BuyerErasureNotReadyError(Exception):
    """Buyer personal-data erasure is not ready."""


def erase_buyer_personal_data(user):
    """
    Future entry point for buyer personal-data erasure.

    This function must not perform erasure until:
    1. Retention requirements are finalized.
    2. Related database records are handled.
    3. Historical financial records are protected.
    4. External file cleanup is implemented.
    5. Automated tests verify the complete workflow.
    """

    if user.user_type != "buyer":
        raise ValueError(
            "Buyer erasure requires a buyer account."
        )

    raise BuyerErasureNotReadyError(
        "Buyer erasure is not implemented. "
        "No personal data has been modified."
    )
