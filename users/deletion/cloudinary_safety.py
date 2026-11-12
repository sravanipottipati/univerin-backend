"""
Safety checks for account-related Cloudinary assets.

No external API calls are made here.
"""

from urllib.parse import urlparse


def validate_cloudinary_reference(reference):
    """
    Validate a candidate Cloudinary public ID.

    This does not prove that the asset belongs to the user.
    Ownership must be verified separately before deletion.
    """
    if not isinstance(reference, str):
        return False

    reference = reference.strip()

    if not reference:
        return False

    if reference.startswith(("http://", "https://")):
        return False

    if reference.startswith("/"):
        return False

    if "\\" in reference:
        return False

    if ".." in reference.split("/"):
        return False

    if "?" in reference or "#" in reference:
        return False

    return True
