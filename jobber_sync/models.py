# jobber_sync/models.py

from decimal import Decimal
from django.db import models
from django.utils import timezone

# We only use Entity as a scope key (allowed).
# We do NOT use Django Ledger CustomerModel or ItemModel.
from django_ledger.models.entity import EntityModel

class JobberToken(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    access_token = models.TextField()
    refresh_token = models.TextField()

    token_type = models.CharField(max_length=50, blank=True, default="Bearer")
    expires_in = models.IntegerField(null=True, blank=True)  # seconds (optional)

    obtained_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"JobberToken({self.created_at:%Y-%m-%d %H:%M})"
    @property
    def is_expired(self) -> bool:
        """
        Treat token as expired if expires_at is missing OR within a 60s buffer.
        """
        if not getattr(self, "expires_at", None):
            return True
        return self.expires_at <= (timezone.now() + timezone.timedelta(seconds=60))


class JobberSyncBase(models.Model):
    """
    Common fields for Jobber-truth tables.
    Keep everything append-safe, idempotent, and audit-friendly.
    """
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    synced_at = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(null=True, blank=True)

    class Meta:
        abstract = True


class JobberClient(JobberSyncBase):
    """
    Jobber truth for a client/customer. NOT Django Ledger CustomerModel.
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_clients",
    )
    jobber_id = models.CharField(max_length=64)

    display_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, default="")
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")

    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")

    # Optional billing snapshot fields (helpful later)
    bill_to_line1 = models.CharField(max_length=255, blank=True, default="")
    bill_to_line2 = models.CharField(max_length=255, blank=True, default="")
    bill_to_city = models.CharField(max_length=100, blank=True, default="")
    bill_to_state = models.CharField(max_length=50, blank=True, default="")
    bill_to_zip = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "jobber_id"],
                name="uq_jobber_client_entity_jobber_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "display_name"], name="ix_jobber_client_name"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.jobber_id})"


class JobberItem(JobberSyncBase):
    """
    Jobber truth for ProductOrService. NOT Django Ledger ItemModel.
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_items",
    )
    jobber_id = models.CharField(max_length=64)

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    category_jobber_id = models.CharField(max_length=64, blank=True, default="")
    category_name = models.CharField(max_length=255, blank=True, default="")

    taxable_default = models.BooleanField(default=False)

    # Jobber truth pricing fields (store if present; don’t infer)
    default_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    internal_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    markup = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    visibility = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "jobber_id"],
                name="uq_jobber_item_entity_jobber_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "name"], name="ix_jobber_item_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.jobber_id})"


class JobberInvoice(JobberSyncBase):
    """
    Jobber truth for invoice header.
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_invoices",
    )
    jobber_id = models.CharField(max_length=64)

    invoice_number = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=50, blank=True, default="")

    issued_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    client = models.ForeignKey(
        JobberClient,
        on_delete=models.PROTECT,
        related_name="invoices",
        null=True,
        blank=True,
    )
    client_jobber_id = models.CharField(max_length=64, blank=True, default="")
    property_jobber_id = models.CharField(max_length=64, blank=True, default="")

    # Jobber totals: store as truth, do not recompute from lines
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    discount_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tip_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    tax_rate_name = models.CharField(max_length=255, blank=True, default="")
    tax_rate_percent = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "jobber_id"],
                name="uq_jobber_invoice_entity_jobber_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "issued_date"], name="ix_jobber_invoice_issued"),
            models.Index(fields=["entity", "status"], name="ix_jobber_invoice_status"),
            models.Index(fields=["entity", "invoice_number"], name="ix_jobber_invoice_number"),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number or self.jobber_id}"


class JobberInvoiceLine(JobberSyncBase):
    """
    Jobber truth for invoice line items.
    """
    invoice = models.ForeignKey(
        JobberInvoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    jobber_line_id = models.CharField(max_length=64)

    item = models.ForeignKey(
        JobberItem,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
        null=True,
        blank=True,
    )
    item_jobber_id = models.CharField(max_length=64, blank=True, default="")

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    taxable = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "jobber_line_id"],
                name="uq_jobber_invoice_line_invoice_jobber_line_id",
            )
        ]
        indexes = [
            models.Index(fields=["invoice", "name"], name="ix_jobber_invline_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} x{self.quantity}"


class JobberPayment(JobberSyncBase):
    """
    Jobber truth for payments.
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_payments",
    )
    jobber_id = models.CharField(max_length=64)

    payment_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    method = models.CharField(max_length=100, blank=True, default="")
    provider = models.CharField(max_length=100, blank=True, default="")
    reference = models.CharField(max_length=255, blank=True, default="")

    invoice = models.ForeignKey(
        JobberInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    invoice_jobber_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "jobber_id"],
                name="uq_jobber_payment_entity_jobber_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "payment_date"], name="ix_jobber_payment_date"),
        ]

    def __str__(self) -> str:
        return f"Payment {self.jobber_id}"


class JobberPayout(JobberSyncBase):
    """
    Jobber truth for payouts/deposits.
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_payouts",
    )
    jobber_id = models.CharField(max_length=64)

    payout_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    destination = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "jobber_id"],
                name="uq_jobber_payout_entity_jobber_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "payout_date"], name="ix_jobber_payout_date"),
        ]

    def __str__(self) -> str:
        return f"Payout {self.jobber_id}"


class JobberPayoutPayment(models.Model):
    """
    Join table: a payout bundles multiple payments.
    """
    payout = models.ForeignKey(JobberPayout, on_delete=models.CASCADE, related_name="payout_payments")
    payment = models.ForeignKey(JobberPayment, on_delete=models.CASCADE, related_name="payment_payouts")

    # Optional allocation amount (some systems split/partial)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payout", "payment"],
                name="uq_jobber_payout_payment_pair",
            )
        ]

class JobberPayoutTransaction(JobberSyncBase):
    """
    Jobber truth for payout balanceTransactions rows.
    Money fields here are integer cents (as proven by Jobber response).
    """
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="jobber_payout_transactions",
    )

    payout = models.ForeignKey(
        JobberPayout,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    # This is balanceTransactions.nodes[].id (EncodedId)
    balance_transaction_id = models.CharField(max_length=255)

    # e.g. PAYMENT, FEE, REFUND, ADJUSTMENT (whatever Jobber returns)
    txn_type = models.CharField(max_length=50)

    gross_cents = models.IntegerField(null=True, blank=True)
    fee_cents = models.IntegerField(null=True, blank=True)
    net_cents = models.IntegerField(null=True, blank=True)

    created = models.DateTimeField(null=True, blank=True)

    # tipAmount appears on PaymentBalanceTransaction; treat as cents unless proven otherwise
    tip_cents = models.IntegerField(null=True, blank=True)

    # Link to Jobber PaymentRecord when this txn is a PaymentBalanceTransaction
    payment = models.ForeignKey(
        "JobberPayment",
        on_delete=models.PROTECT,
        related_name="payout_transactions",
        null=True,
        blank=True,
    )
    payment_record_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "balance_transaction_id"],
                name="uq_jobber_payout_txn_entity_balance_txn_id",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "txn_type"], name="ix_jobber_payout_txn_type"),
            models.Index(fields=["created"], name="ix_jobber_payout_txn_created"),
        ]

    def __str__(self) -> str:
        return f"{self.txn_type} {self.balance_transaction_id}"

