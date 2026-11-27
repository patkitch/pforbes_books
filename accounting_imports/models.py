"""Staging records only: never journal entries."""
from django.db import models


class ImportBatch(models.Model):
    id = models.BigAutoField(primary_key=True)
    account_id = models.PositiveBigIntegerField()
    filename = models.CharField(max_length=255)
    statement_summary = models.JSONField(default=dict, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="undone_import_batches")
    undone_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at", "-pk"]


class ImportRow(models.Model):
    id = models.BigAutoField(primary_key=True)
    PENDING = "pending"
    EXCLUDED = "excluded"
    REVIEWED = "reviewed"
    STATUSES = [(PENDING, "Pending"), (EXCLUDED, "Excluded"), (REVIEWED, "Reviewed — not posted")]
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    account_id = models.PositiveBigIntegerField()
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    source_details = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64)
    occurrence = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUSES, default=PENDING)
    note = models.CharField(max_length=255, blank=True)
    review_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["transaction_date", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["account_id", "fingerprint", "occurrence"],
                name="unique_import_row_per_account_occurrence",
            )
        ]


class WooOrderImport(models.Model):
    id = models.BigAutoField(primary_key=True)
    """Staged WooCommerce order snapshot; never a posted accounting transaction."""
    PENDING = "pending"
    EXCLUDED = "excluded"
    RECEIPTED = "receipted"
    REVIEW_STATES = [
        (PENDING, "Pending review"),
        (EXCLUDED, "Excluded"),
        (RECEIPTED, "Internal receipt created"),
    ]
    source_order_id = models.PositiveBigIntegerField(unique=True)
    order_date = models.DateField()
    woo_status = models.CharField(max_length=30)
    customer_name = models.CharField(max_length=200, blank=True)
    payment_method = models.CharField(max_length=120, blank=True)
    payment_reference = models.CharField(max_length=180, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payload = models.JSONField()
    review_status = models.CharField(max_length=12, choices=REVIEW_STATES, default=PENDING)
    receipt_id = models.PositiveBigIntegerField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-order_date", "-pk"]


class CardPaymentMatch(models.Model):
    id = models.BigAutoField(primary_key=True)
    bank_row = models.ForeignKey(ImportRow, on_delete=models.PROTECT, related_name="bank_payment_matches")
    card_row = models.ForeignKey(ImportRow, on_delete=models.PROTECT, related_name="card_payment_matches")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="created_payment_matches")
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="undone_payment_matches")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["bank_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_bank_payment_match"),
            models.UniqueConstraint(fields=["card_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_card_payment_match"),
        ]


class WooPayoutMatch(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(WooOrderImport, on_delete=models.PROTECT, related_name="payout_matches")
    bank_row = models.ForeignKey(ImportRow, on_delete=models.PROTECT, related_name="woo_payout_matches")
    processor = models.CharField(max_length=20)
    gross = models.DecimalField(max_digits=14, decimal_places=2)
    fee = models.DecimalField(max_digits=14, decimal_places=2)
    net = models.DecimalField(max_digits=14, decimal_places=2)
    evidence = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, related_name="created_woo_payout_matches")
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="undone_woo_payout_matches")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order"], condition=models.Q(undone_at__isnull=True), name="unique_active_woo_order_payout"),
            models.UniqueConstraint(fields=["bank_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_woo_bank_payout"),
        ]
