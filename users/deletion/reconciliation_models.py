"""
Authorization records for account deletion reconciliation.

These records do not authorize storage deletion by themselves.
"""

from django.conf import settings
from django.db import models


class AccountDeletionReconciliationAccess(models.Model):
    administrator = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="deletion_reconciliation_access",
    )

    is_enabled = models.BooleanField(default=False)

    granted_at = models.DateTimeField(
        auto_now_add=True,
    )

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reconciliation_access_grants",
    )

    class Meta:
        verbose_name = "Account deletion reconciliation access"
        verbose_name_plural = "Account deletion reconciliation access"

    def __str__(self):
        return f"Reconciliation access: {self.administrator_id}"


class AccountDeletionReconciliationAudit(models.Model):
    """
    Persistent record of an administrator's reconciliation decision.

    Creating an audit record does not delete assets or finalize jobs.
    """

    class Decision(models.TextChoices):
        INVESTIGATING = "investigating", "Investigating"
        DELETION_CONFIRMED = "deletion_confirmed", "Deletion confirmed"
        ASSET_ABSENT_OBSERVED = "asset_absent_observed", "Asset absent observed"
        ASSET_STILL_EXISTS = "asset_still_exists", "Asset still exists"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    id = models.UUIDField(
        primary_key=True,
        default=__import__("uuid").uuid4,
        editable=False,
    )

    cleanup_job = models.ForeignKey(
        "users.AccountDeletionAsset",
        on_delete=models.PROTECT,
        related_name="reconciliation_audits",
    )

    attempt_id = models.UUIDField()

    administrator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="deletion_reconciliation_audits",
    )

    decision = models.CharField(
        max_length=30,
        choices=Decision.choices,
    )

    evidence_reference = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )

    explanation = models.TextField()

    # Immutable asset identity captured during read-only verification.
    verified_storage_reference = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )

    verified_resource_type = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    verified_storage_provider = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["cleanup_job", "created_at"],
                name="deletion_recon_job_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "Reconciliation audit records cannot be modified."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "Reconciliation audit records cannot be deleted."
        )

    def __str__(self):
        return f"{self.cleanup_job_id}: {self.decision}"
