
import uuid

from django.db import models


class VincentDraftSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        UNCERTAIN = "uncertain", "Needs Review"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    woo_product_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )
    
    artwork_snapshot = models.JSONField(
        null=True,
        blank=True,
        default=None,
    )

    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Vincent submission {self.id} ({self.status})"

