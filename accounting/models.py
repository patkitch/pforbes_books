from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Account(models.Model):
    """Business COA identity is its PK, not its editable four-digit number."""

    TYPES = [
        ("asset", "Asset"),
        ("liability", "Liability"),
        ("equity", "Equity"),
        ("income", "Income"),
        ("cogs", "Cost of Goods Sold"),
        ("expense", "Operating Expense"),
        ("other_income", "Other Income"),
        ("other_expense", "Other Expense"),
    ]
    BALANCES = [("debit", "Debit"), ("credit", "Credit")]
    DEFAULT_BALANCES = {
        "asset": "debit", "liability": "credit", "equity": "credit",
        "income": "credit", "cogs": "debit", "expense": "debit",
        "other_income": "credit", "other_expense": "debit",
    }
    number = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=180)
    account_type = models.CharField(max_length=20, choices=TYPES)
    # Blank on older records means the standard balance for their account type.
    # This permits a safe additive migration without rewriting prior journals.
    normal_balance = models.CharField(
        max_length=6, choices=BALANCES, blank=True, default=""
    )
    detail_type = models.CharField(max_length=120, blank=True)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    is_active = models.BooleanField(default=True)
    memo = models.TextField(blank=True)

    class Meta:
        ordering = ["number", "name"]

    def clean(self):
        super().clean()
        if not (len(self.number) == 4 and self.number.isascii() and self.number.isdigit()):
            raise ValidationError({"number": "Account number must contain exactly four digits."})
        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError({"parent": "An account cannot be its own parent."})
            if self.parent.account_type != self.account_type:
                raise ValidationError({"parent": "Parent and child must use the same account type."})
            seen = {self.pk} if self.pk else set()
            current = self.parent
            while current:
                if current.pk in seen:
                    raise ValidationError({"parent": "Parent hierarchy must not contain a cycle."})
                seen.add(current.pk)
                current = current.parent

    @property
    def normal_side(self):
        return self.normal_balance or self.DEFAULT_BALANCES[self.account_type]

    @property
    def normal_side_label(self):
        return self.normal_side.title()

    def __str__(self):
        return f"{self.number} — {self.name}"


class JournalEntry(models.Model):
    STATUSES = [("draft", "Draft"), ("posted", "Posted"), ("reversed", "Reversed")]
    date = models.DateField()
    payee = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=255, blank=True)
    memo = models.TextField(blank=True)
    source = models.CharField(max_length=80, default="manual")
    source_reference = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reversed_by_entry = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reverses_entry"
    )

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_reference"],
                condition=~Q(source_reference=""),
                name="accounting_unique_source_reference",
            ),
        ]

    def __str__(self):
        return f"{self.date} — {self.description or self.payee or self.pk}"


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, related_name="lines", on_delete=models.PROTECT)
    account = models.ForeignKey(Account, related_name="journal_lines", on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    memo = models.CharField(max_length=255, blank=True)

    def clean(self):
        super().clean()
        if self.debit < 0 or self.credit < 0 or bool(self.debit) == bool(self.credit):
            raise ValidationError("Exactly one of debit and credit must be positive on each line.")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name="accounting_one_positive_side",
            )
        ]


class AuditEvent(models.Model):
    entry = models.ForeignKey(JournalEntry, related_name="audit_events", on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class SalesTaxRecord(models.Model):
    """Cash-basis sales-tax information for a sale; posted journal is the ledger source.

    Tax rates are supplied by Stripe or by user lookup, never invented here.
    A record may represent a gallery-managed sale (no own tax collected).
    """
    SOURCES = [
        ("stripe", "Stripe / WooCommerce"), ("cash", "Cash sale"),
        ("gallery", "Gallery-managed"), ("other", "Other"),
    ]
    sale_date = models.DateField()
    source = models.CharField(max_length=15, choices=SOURCES)
    jurisdiction = models.CharField(max_length=160, blank=True)
    sale_amount = models.DecimalField(max_digits=14, decimal_places=2)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_collected = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    authority = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="sales_tax_records", null=True, blank=True)
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name="sales_tax_record", null=True, blank=True)
    memo = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.sale_amount < 0 or self.taxable_amount < 0 or self.tax_collected < 0:
            raise ValidationError("Sales amounts and collected tax cannot be negative.")
        if self.taxable_amount > self.sale_amount:
            raise ValidationError("Taxable sales cannot exceed total sales.")
        if self.source == "gallery" and self.tax_collected:
            raise ValidationError("Gallery-managed sales tax is remitted by the gallery.")
        if self.source != "gallery" and self.tax_collected and not self.authority_id:
            raise ValidationError("Choose a tax payable account when you collect sales tax.")
        if self.authority_id and self.authority.account_type != "liability":
            raise ValidationError("Tax payable account must be a liability.")

    class Meta:
        ordering = ["-sale_date", "-pk"]


class SalesTaxPayment(models.Model):
    """Quarterly filing/payment history, including zero-dollar cash payments.

    Zero payments do not create journal entries; positive ones debit sales tax
    payable and credit the selected asset account.
    """
    authority = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="tax_payments")
    quarter = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    bank_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="tax_payments_from")
    memo = models.TextField(blank=True)
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="sales_tax_payment")

    def clean(self):
        super().clean()
        if self.quarter not in (1, 2, 3, 4):
            raise ValidationError("Choose quarter 1 through 4.")
        if self.amount < 0:
            raise ValidationError("Sales tax payment cannot be negative.")
        if self.authority_id and self.authority.account_type != "liability":
            raise ValidationError("Payment authority account must be a liability.")
        if self.bank_account_id and self.bank_account.account_type != "asset":
            raise ValidationError("Choose a bank or cash asset account.")

    class Meta:
        ordering = ["-year", "-quarter", "-paid_on", "-pk"]
