# forbes_lawn_billing/models.py

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django_ledger.models.entity import EntityModel, CustomerModel # if this errors, we’ll adjust path
from django_ledger.models import JournalEntryModel

class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    PARTIALLY_PAID = "PARTIAL", "Partially Paid"
    PAID = "PAID", "Paid"
    VOID = "VOID", "Void"


class Invoice(models.Model):
    """
    Forbes Lawn invoice that *looks/behaves* like QuickBooks.
    This is YOUR invoice model. Later we'll add a helper to post
    summarized entries into Django Ledger (cash-basis).
    """

    # --- Core relationships ---

    # TODO: point these to your actual Django Ledger models
    # entity = models.ForeignKey("django_ledger.EntityModel", on_delete=models.PROTECT)
    # customer = models.ForeignKey("django_ledger.CustomerModel", on_delete=models.PROTECT)

    # For now, keep it simple; you can replace these later:
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name="forbes_lawn_invoices",
        help_text="Django Ledger entity this invoice belongs to (e.g. Forbes Lawn Spraying LLC).",
        null=True,      # ← add this
        blank=True,     # ← and this
    )
    # NEW: Link to Django Ledger CustomerModel
    customer = models.ForeignKey(
        CustomerModel,
        on_delete=models.PROTECT,
        related_name="forbes_lawn_invoices",
        null=True,
        blank=True,
        help_text="Django Ledger customer record. Optional for now; will become required later."
    )

    # Existing snapshot / display name
    customer_name = models.CharField(
        max_length=200,
        help_text="Display name for the customer at time of invoicing."
    )

    # ... rest of your fields ...

    def save(self, *args, **kwargs):
        # If a CustomerModel is set but customer_name is empty, sync it.
        if self.customer and not self.customer_name:
            # CustomerModel usually has 'customer_name' field
            self.customer_name = self.customer.customer_name
        super().save(*args, **kwargs)

    

    # --- Jobber metadata (header-level) ---
    jobber_invoice_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Original Jobber invoice ID (for imports/sync).",
    )
    jobber_client_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Jobber client/customer ID.",
    )
    jobber_property_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Jobber property/service location ID.",
    )

    # Optionally store a foreign key to your ledger Customer when you’re ready:
    # customer_ledger = models.ForeignKey(
    #     "django_ledger.CustomerModel",
    #     null=True, blank=True,
    #     on_delete=models.SET_NULL,
    # )
    jobber_job_numbers_raw = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Raw Jobber Job #s from invoice export, e.g. '1219' or '1226,1225'."
)


    # --- Invoice identity / dates / terms ---

    invoice_number = models.CharField(
        max_length=50,
        help_text="Visible invoice number (e.g. 492).",
    )
    status = models.CharField(
        max_length=10,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )

    terms = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. Due on receipt, Net 30.",
    )

    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    # --- Contact / addresses / email ---

    email_to = models.EmailField(blank=True)
    email_cc = models.CharField(max_length=255, blank=True)
    email_bcc = models.CharField(max_length=255, blank=True)

    bill_to_name = models.CharField(max_length=200, blank=True)
    bill_to_line1 = models.CharField(max_length=200, blank=True)
    bill_to_line2 = models.CharField(max_length=200, blank=True)
    bill_to_city = models.CharField(max_length=100, blank=True)
    bill_to_state = models.CharField(max_length=50, blank=True)
    bill_to_zip = models.CharField(max_length=20, blank=True)
    bill_to_country = models.CharField(max_length=100, blank=True)

    

    

    tags = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated tags, replacing QB 'Tags (hidden)'.",
    )

    # --- Customer-facing text ---

    payment_instructions = models.TextField(
        blank=True,
        help_text="Customer payment options / how you want to be paid.",
    )
    note_to_customer = models.TextField(blank=True)
    memo_on_statement = models.TextField(
        blank=True,
        help_text="Internal statement memo (won't show on invoice PDF).",
    )

    # --- Monetary fields (snapshot at time of save) ---

    # Subtotal of all line items before discounts and tax
    subtotal = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Invoice-level discount (QuickBooks has % + amount; we store both)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    taxable_subtotal = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Tax settings
    tax_rate_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. 'Automatic Calculation' or a named tax setup.",
    )
    tax_rate_percent = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000")
    )
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Overall totals
    total = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text="Invoice total before deposits/payments.",
    )
    deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Sum of all payments (including the one shown as 'Payment on 04/16/2015')
    amount_paid = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    balance_due = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Convenience flag for things like the green "Paid in full" banner
    paid_in_full = models.BooleanField(default=False)

    # --- Meta / audit ---

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
        # --- Ledger posting metadata ---
    ar_journal_entry = models.ForeignKey(
        JournalEntryModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="forbes_lawn_invoices_ar",
        help_text="JE that posts AR + revenue + tax for this invoice.",
    ) 
    

    class Meta:
        ordering = ["-invoice_date", "-id"]

      

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer_name}"

    # --- Simple recompute helpers (you can call these in forms/views) ---

    def recompute_totals_from_lines(self):
        """
        Recalculate subtotal, taxable_subtotal, discount_amount, tax_amount,
        total, balance_due based on line items and payments.
        """

        from decimal import Decimal
        from django.db.models import Sum

        # 1) Recompute each line_amount from quantity * rate
        lines_qs = self.lines.all()
        for line in lines_qs:
            line.recompute_amount()
            line.save(update_fields=["line_amount"])

        lines = list(lines_qs)

        # 2) Subtotals
        self.subtotal = sum((l.line_amount for l in lines), Decimal("0.00"))
        self.taxable_subtotal = sum(
            (l.line_amount for l in lines if l.taxable),
            Decimal("0.00"),
        )

        # 3) Discount
        if self.discount_percent:
            self.discount_amount = (
                self.subtotal * self.discount_percent / Decimal("100.0")
            ).quantize(Decimal("0.01"))
        else:
            self.discount_amount = self.discount_amount or Decimal("0.00")

        taxable_base = self.taxable_subtotal - self.discount_amount
        if taxable_base < 0:
            taxable_base = Decimal("0.00")

        # 4) Tax
        self.tax_amount = (
            taxable_base * self.tax_rate_percent / Decimal("100.0")
        ).quantize(Decimal("0.01"))

        # 5) Total before deposits/payments
        self.total = (
            self.subtotal - self.discount_amount + self.tax_amount
        ).quantize(Decimal("0.01"))

        # 6) Payments and balance
        payments_total = (
            self.payments.aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        self.amount_paid = payments_total
        self.balance_due = (
            self.total - self.deposit_amount - self.amount_paid
        ).quantize(Decimal("0.01"))

        self.paid_in_full = self.balance_due <= Decimal("0.00")

        if self.paid_in_full:
            self.status = InvoiceStatus.PAID
        elif payments_total > 0:
            self.status = InvoiceStatus.PARTIALLY_PAID
        else:
            # Only mark OPEN if it was DRAFT/OPEN before; VOID stays VOID
            if self.status != InvoiceStatus.VOID:
                self.status = InvoiceStatus.OPEN
    
class InvoiceLine(models.Model):
    """
    Line items on the invoice, matching the QB columns:
    Service Date, Product/Service, Description, Qty, Rate, Amount, Tax.
    """

    invoice = models.ForeignKey(
        Invoice,
        related_name="lines",
        on_delete=models.CASCADE,
    )
    # --- Jobber metadata (line-level) ---
    jobber_line_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Jobber line item ID.",
    )
    jobber_service_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Jobber service/product ID.",
    )

    line_number = models.PositiveIntegerField(default=1)

    service_date = models.DateField(null=True, blank=True)

    # 🔹 Link to Django Ledger ItemModel (non-inventory service item)
    item_model = models.ForeignKey(
        "django_ledger.ItemModel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="forbes_lawn_invoice_lines",
        help_text="Linked Django Ledger Item (service/product).",
    )
      # Snapshot name (what was on the invoice at the time)
    item_name = models.CharField(
        max_length=200,
        help_text="Product/Service name as shown on the invoice.",
    ) 
    

    description = models.CharField(max_length=255, blank=True)

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    line_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    taxable = models.BooleanField(default=True)

    class Meta:
        ordering = ["line_number", "id"]

    def __str__(self):
        return f"{self.item_name} ({self.line_amount})"

    def recompute_amount(self):
        self.line_amount = (self.quantity * self.rate).quantize(Decimal("0.01"))
class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    CARD = "CARD", "Credit card"
    ACH = "ACH", "Bank payment (ACH)"
    CHECK = "CHECK", "Check"
    OTHER = "OTHER", "Other"


class InvoicePayment(models.Model):
    """
    Individual payments applied to an invoice.
    These drive the 'Payment on <date>' lines and the Balance Due.
    """

    invoice = models.ForeignKey(
        "forbes_lawn_billing.Invoice",
        related_name="payments",
        on_delete=models.CASCADE,
    )

    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    # (optional) raw Jobber fields, if you don’t already have them:
    jobber_type = models.CharField(max_length=50, blank=True)
    jobber_paid_with = models.CharField(max_length=50, blank=True)
    jobber_paid_through = models.CharField(max_length=50, blank=True)

    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Check no., transaction id, etc.",
    )
    # NEW: Jobber identity
    jobber_payment_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Unique payment ID from Jobber (for deduping imports).",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    payment_journal_entry = models.ForeignKey(
        JournalEntryModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="forbes_lawn_invoice_payments",
        help_text="JE that moves AR → Payments to Deposit.",
    )


    class Meta:
        ordering = ["-payment_date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "jobber_payment_id"],
                condition=~models.Q(jobber_payment_id__isnull=True),
                name="uniq_jobber_payment_per_invoice",
            )
        ]
        # Ledger posting metadata
    
    def __str__(self):
        return f"Payment {self.amount} on {self.payment_date} ({self.get_payment_method_display()})"
def invoice_attachment_upload_to(instance, filename):
    return f"invoices/{instance.invoice_id}/{filename}"


class InvoiceAttachment(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        related_name="attachments",
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to=invoice_attachment_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for Invoice {self.invoice_id}"

