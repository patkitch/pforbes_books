"""Contacts and receipt records separate from the immutable journal schema."""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    address1 = models.CharField(max_length=200, blank=True)
    address2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=24, blank=True)
    country = models.CharField(max_length=80, blank=True, default="United States")
    notes = models.TextField(blank=True)
    default_account_number = models.CharField(
        max_length=4, blank=True,
        help_text="Suggested account number only; never auto-post."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    kind = models.CharField(
        max_length=20, choices=(("person", "Individual"), ("organization", "Organization")),
        default="person"
    )
    billing_address1 = models.CharField(max_length=200, blank=True)
    billing_address2 = models.CharField(max_length=200, blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100, blank=True)
    billing_postal_code = models.CharField(max_length=24, blank=True)
    billing_country = models.CharField(max_length=80, blank=True)
    shipping_address1 = models.CharField(max_length=200, blank=True)
    shipping_address2 = models.CharField(max_length=200, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=24, blank=True)
    shipping_country = models.CharField(max_length=80, blank=True)
    woo_customer_id = models.PositiveBigIntegerField(
        unique=True, null=True, blank=True,
        help_text="WooCommerce registered customer ID. Never use guest ID 0."
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class TransactionParty(models.Model):
    """Validated pointer to a journal entry; legacy accounting has local-only migrations.

    This independent app deliberately stores the numeric journal ID instead of
    introducing a fragile cross-app migration dependency. Use service methods
    to validate that the journal entry exists before creating a link.
    """
    journal_entry_id = models.PositiveBigIntegerField(unique=True, db_index=True)
    vendor = models.ForeignKey(
        Vendor, null=True, blank=True, on_delete=models.PROTECT,
        related_name="transaction_links"
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT,
        related_name="transaction_links"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if bool(self.vendor_id) == bool(self.customer_id):
            raise ValidationError("Select one vendor or one customer.")
        from accounting.models import JournalEntry
        if self.journal_entry_id and not JournalEntry.objects.filter(pk=self.journal_entry_id).exists():
            raise ValidationError("Accounting transaction does not exist.")

    class Meta:
        ordering = ("-pk",)


class Receipt(models.Model):
    TYPES = (
        ("purchase", "Purchase receipt"),
        ("sale", "Sales receipt"),
        ("refund", "Refund documentation"),
        ("other", "Other document"),
    )
    title = models.CharField(max_length=200)
    receipt_type = models.CharField(max_length=20, choices=TYPES)
    date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    vendor = models.ForeignKey(
        Vendor, null=True, blank=True, on_delete=models.PROTECT,
        related_name="receipts"
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT,
        related_name="receipts"
    )
    journal_entry_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=40, default="manual")
    source_reference = models.CharField(max_length=180, blank=True)
    attachment = models.FileField(upload_to="accounting_receipts/%Y/%m/", blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "Amount cannot be negative."})
        if self.vendor_id and self.customer_id:
            raise ValidationError("A receipt may link to a vendor or customer, not both.")
        if self.receipt_type == "purchase" and self.customer_id:
            raise ValidationError("Purchase receipts cannot be assigned to customers.")
        if self.receipt_type == "sale" and self.vendor_id:
            raise ValidationError("Sales receipts cannot be assigned to vendors.")
        if self.journal_entry_id:
            from accounting.models import JournalEntry
            if not JournalEntry.objects.filter(pk=self.journal_entry_id).exists():
                raise ValidationError({"journal_entry_id": "Accounting transaction does not exist."})

    class Meta:
        ordering = ("-date", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "source_reference"),
                condition=~Q(source_reference=""),
                name="ac_contact_unique_receipt_source",
            ),
        ]

    def __str__(self):
        return self.title


class ReceiptItem(models.Model):
    """Itemized artwork on a sales receipt; does not create journal lines."""
    ITEM_TYPES = (("original", "Original artwork"), ("print", "Fine art print"), ("other", "Other item"))
    receipt = models.ForeignKey(Receipt, related_name="items", on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(default=1)
    artwork_title = models.CharField(max_length=200)
    item_type = models.CharField(max_length=16, choices=ITEM_TYPES)
    size = models.CharField(max_length=80, blank=True, help_text="For example, 11x14 print or 24x36 original.")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("position", "pk")

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least one."})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})
        if self.receipt_id and self.receipt.receipt_type != "sale":
            raise ValidationError("Artwork line items are available on sales receipts only.")

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.artwork_title
