"""
Generate internal identifiers for anonymized accounts.

These identifiers must never be used as real phone numbers.
"""

from users.models import User


def generate_anonymized_phone():
    """
    Return an unused 10-character internal identifier.

    The caller must handle database uniqueness conflicts
    when saving, because concurrent requests are possible.
    """
    import secrets

    for _ in range(100):
        candidate = "d" + str(
            secrets.randbelow(1_000_000_000)
        ).zfill(9)

        if not User.objects.filter(
            phone_number=candidate
        ).exists():
            return candidate

    raise RuntimeError(
        "Unable to generate a unique anonymized identifier."
    )
