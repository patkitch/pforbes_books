"""Staging records only: never journal entries."""
from django.db import models


class ImportBatch(models.Model):
    account_id = models.PositiveBigIntegerField()
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at", "-pk"]


class ImportRow(models.Model):
    PENDING = "pending"
    EXCLUDED = "excluded"
    STATUSES = [(PENDING, "Pending"), (EXCLUDED, "Excluded")]
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    account_id = models.PositiveBigIntegerField()
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    fingerprint = models.CharField(max_length=64)
    occurrence = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUSES, default=PENDING)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["transaction_date", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "fingerprint", "occurrence"],
                name="unique_import_row_per_account_occurrence",
            )
        ]
