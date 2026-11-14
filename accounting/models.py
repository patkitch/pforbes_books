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
    number = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=180)
    account_type = models.CharField(max_length=20, choices=TYPES)
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
