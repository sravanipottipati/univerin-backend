"""Restricted Google Play reviewer OTP configuration."""

import hmac
import json
import os
import re


def get_review_accounts():
    """Return validated reviewer phone-to-OTP mappings."""
    raw = os.environ.get("PLAY_REVIEW_OTP_ACCOUNTS", "")

    if not raw:
        return {}

    try:
        accounts = json.loads(raw)
    except (ValueError, TypeError):
        return {}

    if not isinstance(accounts, dict):
        return {}

    if not all(
        isinstance(phone, str)
        and re.fullmatch(r"[0-9]{10}", phone)
        and isinstance(otp, str)
        and re.fullmatch(r"[0-9]{6}", otp)
        for phone, otp in accounts.items()
    ):
        return {}

    return accounts


def is_review_account(phone_number):
    return phone_number in get_review_accounts()


def verify_review_otp(phone_number, otp):
    expected = get_review_accounts().get(phone_number)

    if expected is None or not isinstance(otp, str):
        return False

    return hmac.compare_digest(expected, otp)


# Dedicated Google Play reviewer accounts.
# These restrictions do not depend on OTP environment configuration.
RESTRICTED_REVIEW_PHONES = frozenset({
    "9999999991",  # Buyer reviewer
    "9999999992",  # Seller reviewer
    "9999999993",  # Delivery Partner reviewer
})


def is_restricted_review_account(phone_number):
    """Identify reviewer accounts independently of OTP settings."""
    return str(phone_number) in RESTRICTED_REVIEW_PHONES
