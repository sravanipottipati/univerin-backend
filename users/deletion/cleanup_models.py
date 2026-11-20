"""
Persistent cleanup records for account deletion.

Creating a cleanup record does not delete any external asset.
"""

import uuid

from django.db import models


class AccountDeletionAsset(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    deletion_request = models.ForeignKey(
        "users.AccountDeletionRequest",
        on_delete=models.CASCADE,
        related_name="asset_cleanup_jobs",
    )

    owner_type = models.CharField(max_length=30)
    field_name = models.CharField(max_length=100)

    # Must be verified against the originating model field
    # before any external deletion is attempted.
    storage_reference = models.TextField()

    # Cloudinary requires the correct resource type for deletion.
    resource_type = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    attempts = models.PositiveIntegerField(default=0)

    # Identifies the current worker attempt.
    attempt_id = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )

    # Expiration indicates that manual reconciliation is needed.
    lease_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    last_error = models.TextField(blank=True, default="")

    # Set only after the approved storage adapter reports success.
    # Must be tied to the current cleanup attempt.
    storage_deletion_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "deletion_request",
                    "owner_type",
                    "field_name",
                ],
                name="unique_deletion_asset_field",
            )
        ]

    def __str__(self):
        return f"{self.owner_type}.{self.field_name}: {self.status}"
