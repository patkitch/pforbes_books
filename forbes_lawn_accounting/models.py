"""
Forbes Lawn Accounting Models
2026 forward - Clean architecture with Jobber integration

Model hierarchy:
1. Customer (from Jobber clients)
2. ServiceItem (from Jobber products/services)
3. Invoice → InvoiceLine → InvoicePayment
4. BankDeposit (Phase 2)
5. Vendor → VendorBill → VendorPayment (Phase 3)
6. Tax & Reconciliation models (Phase 4)
"""

from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

# Django Ledger imports
from django_ledger.models.entity import EntityModel
from django_ledger.models.customer import CustomerModel
from django_ledger.models.items import ItemModel
from django_ledger.models.chart_of_accounts import ChartOfAccountModel
from django_ledger.models.journal_entry import JournalEntryModel

User = get_user_model()


# ============================================================================
# PHASE 1: CUSTOMER & INVOICING (from Jobber)
# ============================================================================

class Customer(models.Model):
    """
    Forbes Lawn customer - synced from Jobber.
    
    Maps to Django Ledger CustomerModel for accounting integration.
    Stores Jobber metadata for sync/deduplication.
    
    Sync: JobberClient → Customer → Django Ledger CustomerModel
    """
    # Django Ledger relationships
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name='forbes_lawn_customers',
        help_text="Forbes Lawn Spraying LLC entity"
    )
    
    ledger_customer = models.ForeignKey(
        CustomerModel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='forbes_lawn_customer',
        help_text="Link to Django Ledger customer record"
    )
    
    # Jobber metadata for sync
    jobber_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Jobber client ID (for deduplication)"
    )
    
    jobber_client_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Jobber's client identifier"
    )
    
    # Customer information
    name = models.CharField(
        max_length=255,
        help_text="Customer display name"
    )
    
    company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Company name if business customer"
    )
    
    email = models.EmailField(
        blank=True,
        help_text="Primary email address"
    )
    
    phone = models.CharField(
        max_length=50,
        blank=True,
        help_text="Primary phone number"
    )
    
    # Billing address
    billing_address_line1 = models.CharField(max_length=255, blank=True)
    billing_address_line2 = models.CharField(max_length=255, blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=50, blank=True)
    billing_zip = models.CharField(max_length=20, blank=True)
    
    # Service address (where work is performed)
    service_address_line1 = models.CharField(max_length=255, blank=True)
    service_address_line2 = models.CharField(max_length=255, blank=True)
    service_city = models.CharField(max_length=100, blank=True)
    service_state = models.CharField(max_length=50, blank=True)
    service_zip = models.CharField(max_length=20, blank=True)
    
    # Status
    active = models.BooleanField(
        default=True,
        help_text="Is this customer active?"
    )
    
    # Sync metadata
    synced_at = models.DateTimeField(
        help_text="When this record was last synced from Jobber"
    )
    
    jobber_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON response from Jobber API (for debugging)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'forbes_lawn_customer'
        ordering = ['name']
        indexes = [
            models.Index(fields=['entity', 'name']),
            models.Index(fields=['entity', 'active']),
            models.Index(fields=['jobber_id']),
        ]
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
    
    def __str__(self):
        return self.name
    
    @property
    def full_billing_address(self):
        """Return formatted billing address."""
        parts = [
            self.billing_address_line1,
            self.billing_address_line2,
            f"{self.billing_city}, {self.billing_state} {self.billing_zip}".strip()
        ]
        return "\n".join([p for p in parts if p])
    
    @property
    def full_service_address(self):
        """Return formatted service address."""
        parts = [
            self.service_address_line1,
            self.service_address_line2,
            f"{self.service_city}, {self.service_state} {self.service_zip}".strip()
        ]
        return "\n".join([p for p in parts if p])
    
    def get_balance(self):
        """
        Get current AR balance for this customer.
        Returns total of unpaid invoices.
        """
        from django.db.models import Sum
        balance = self.invoices.filter(
            status__in=['OPEN', 'PARTIAL']
        ).aggregate(
            total=Sum('balance_due')
        )['total'] or Decimal('0.00')
        return balance


class ServiceItem(models.Model):
    """
    Service items (lawn care services) - synced from Jobber.
    
    Represents services like:
    - Fertilization
    - Weed Control
    - Lime Application
    - Grass Seeding
    - etc.
    
    Maps to Django Ledger ItemModel for accounting integration.
    Each service maps to a revenue account (4024 Taxable or 4025 Non-Taxable).
    
    Sync: JobberItem → ServiceItem → Django Ledger ItemModel
    """
    # Django Ledger relationships
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name='forbes_lawn_service_items',
        help_text="Forbes Lawn Spraying LLC entity"
    )
    
    ledger_item = models.ForeignKey(
        ItemModel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='forbes_lawn_service_item',
        help_text="Link to Django Ledger item record"
    )
    
    # Jobber metadata
    jobber_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Jobber product/service ID (for deduplication)"
    )
    
    # Service information
    name = models.CharField(
        max_length=255,
        help_text="Service name (e.g., 'Fertilization Round 1')"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Detailed description of service"
    )
    
    # Category (from Jobber)
    category_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Jobber category (e.g., 'Fertilization', 'Weed Control')"
    )
    
    # Pricing
    default_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Default price for this service"
    )
    
    # Tax handling
    taxable = models.BooleanField(
        default=True,
        help_text="Is this service subject to sales tax?"
    )
    
    # Revenue account mapping
    revenue_account = models.ForeignKey(
        'django_ledger.AccountModel',  # Changed from ChartOfAccountModel to AccountModel
        on_delete=models.PROTECT,
        related_name='forbes_lawn_service_items',
        help_text="COA account for revenue (4024 Taxable or 4025 Non-Taxable)"
    )
    
    # Status
    active = models.BooleanField(
        default=True,
        help_text="Is this service actively offered?"
    )
    
    # Sync metadata
    synced_at = models.DateTimeField(
        help_text="When this record was last synced from Jobber"
    )
    
    jobber_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON response from Jobber API (for debugging)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'forbes_lawn_service_item'
        ordering = ['category_name', 'name']
        indexes = [
            models.Index(fields=['entity', 'name']),
            models.Index(fields=['entity', 'active']),
            models.Index(fields=['entity', 'category_name']),
            models.Index(fields=['jobber_id']),
        ]
        verbose_name = 'Service Item'
        verbose_name_plural = 'Service Items'
    
    def __str__(self):
        return self.name
    
    @property
    def revenue_account_code(self):
        """Return the COA code (e.g., '4024')."""
        return self.revenue_account.code if self.revenue_account else None
    
    @property
    def revenue_account_name(self):
        """Return the full COA account name."""
        return self.revenue_account.name if self.revenue_account else None


class InvoiceStatus(models.TextChoices):
    """Invoice status choices."""
    DRAFT = 'DRAFT', 'Draft'
    OPEN = 'OPEN', 'Open'
    PARTIAL = 'PARTIAL', 'Partially Paid'
    PAID = 'PAID', 'Paid'
    VOID = 'VOID', 'Void'


class Invoice(models.Model):
    """
    Customer invoice - synced from Jobber.
    
    Represents a Forbes Lawn invoice with:
    - Customer and service details
    - Line items (services performed)
    - Tax calculation
    - Payment tracking
    
    Auto-posts to ledger:
      DR 1010 Accounts Receivable
      CR 4024/4025 Service Income
      CR 2024 Sales Tax to Pay
    
    Sync: JobberInvoice → Invoice → Journal Entry
    """
    # Core relationships
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name='forbes_lawn_accounting_invoices',  # Changed to be unique
        help_text="Forbes Lawn Spraying LLC entity"
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='invoices',
        help_text="Customer being invoiced"
    )
    
    # Jobber metadata
    jobber_invoice_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Jobber invoice ID (for deduplication)"
    )
    
    jobber_job_numbers = models.CharField(
        max_length=255,
        blank=True,
        help_text="Jobber job numbers (e.g., '1219, 1225')"
    )
    
    # Invoice details
    invoice_number = models.CharField(
        max_length=50,
        help_text="Visible invoice number (e.g., '492')"
    )
    
    invoice_date = models.DateField(
        help_text="Date invoice was issued"
    )
    
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Payment due date"
    )
    
    status = models.CharField(
        max_length=10,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )
    
    # Amounts (calculated from lines)
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all line items before tax"
    )
    
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Invoice-level discount"
    )
    
    taxable_subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of taxable line items"
    )
    
    tax_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Tax rate as decimal (e.g., 0.0865 for 8.65%)"
    )
    
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sales tax amount"
    )
    
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total invoice amount (subtotal - discount + tax)"
    )
    
    # Payment tracking
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Sum of all payments received"
    )
    
    balance_due = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Remaining balance (total - amount_paid)"
    )
    
    # Notes
    note_to_customer = models.TextField(
        blank=True,
        help_text="Customer-visible note on invoice"
    )
    
    internal_notes = models.TextField(
        blank=True,
        help_text="Internal notes (not shown to customer)"
    )
    
    # Ledger posting metadata
    ar_journal_entry = models.ForeignKey(
        JournalEntryModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='forbes_lawn_accounting_invoices_ar',  # Changed to be unique
        help_text="Journal entry that posts AR + Revenue + Tax"
    )
    
    posted_to_ledger = models.BooleanField(
        default=False,
        help_text="Has this invoice been posted to the ledger?"
    )
    
    posted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this invoice was posted to ledger"
    )
    
    # Sync metadata
    synced_at = models.DateTimeField(
        help_text="When this record was last synced from Jobber"
    )
    
    jobber_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON response from Jobber API"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'forbes_lawn_invoice'
        ordering = ['-invoice_date', '-invoice_number']
        indexes = [
            models.Index(fields=['entity', 'invoice_date']),
            models.Index(fields=['entity', 'customer', 'status']),
            models.Index(fields=['entity', 'status', 'balance_due']),
            models.Index(fields=['jobber_invoice_id']),
            models.Index(fields=['invoice_number']),
        ]
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
    
    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"
    
    def recompute_totals(self):
        """
        Recalculate all totals from line items and payments.
        Should be called after adding/removing lines or payments.
        """
        from django.db.models import Sum
        
        # Recompute each line amount first
        for line in self.lines.all():
            line.recompute_amount()
            line.save(update_fields=['amount'])
        
        # Subtotals
        lines = list(self.lines.all())
        self.subtotal = sum((line.amount for line in lines), Decimal('0.00'))
        self.taxable_subtotal = sum(
            (line.amount for line in lines if line.taxable),
            Decimal('0.00')
        )
        
        # Tax
        taxable_base = self.taxable_subtotal - self.discount_amount
        if taxable_base < 0:
            taxable_base = Decimal('0.00')
        
        self.tax_amount = (taxable_base * self.tax_rate).quantize(Decimal('0.01'))
        
        # Total
        self.total = (
            self.subtotal - self.discount_amount + self.tax_amount
        ).quantize(Decimal('0.01'))
        
        # Payments
        payments_total = (
            self.payments.aggregate(total=Sum('amount'))['total']
            or Decimal('0.00')
        )
        self.amount_paid = payments_total
        self.balance_due = (self.total - self.amount_paid).quantize(Decimal('0.01'))
        
        # Status
        if self.balance_due <= Decimal('0.00'):
            self.status = InvoiceStatus.PAID
        elif payments_total > 0:
            self.status = InvoiceStatus.PARTIAL
        elif self.status not in [InvoiceStatus.VOID, InvoiceStatus.DRAFT]:
            self.status = InvoiceStatus.OPEN
        
        self.save()


class InvoiceLine(models.Model):
    """
    Invoice line item - represents a service performed.
    
    Each line:
    - Links to a ServiceItem (what was done)
    - Has quantity, rate, and calculated amount
    - Has taxable flag
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='lines',
        help_text="Invoice this line belongs to"
    )
    
    # Jobber metadata
    jobber_line_id = models.CharField(
        max_length=64,
        help_text="Jobber line item ID"
    )
    
    # Service item
    service_item = models.ForeignKey(
        ServiceItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='invoice_lines',
        help_text="Service performed"
    )
    
    # Line details
    line_number = models.PositiveIntegerField(
        help_text="Line order on invoice"
    )
    
    service_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date service was performed"
    )
    
    description = models.CharField(
        max_length=255,
        help_text="Service description"
    )
    
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text="Quantity of service"
    )
    
    rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price per unit"
    )
    
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Line total (quantity × rate)"
    )
    
    taxable = models.BooleanField(
        default=True,
        help_text="Is this line subject to sales tax?"
    )
    
    class Meta:
        db_table = 'forbes_lawn_invoice_line'
        ordering = ['line_number']
        unique_together = [['invoice', 'jobber_line_id']]
        indexes = [
            models.Index(fields=['invoice', 'line_number']),
        ]
        verbose_name = 'Invoice Line'
        verbose_name_plural = 'Invoice Lines'
    
    def __str__(self):
        return f"{self.description} - ${self.amount}"
    
    def recompute_amount(self):
        """Recalculate line amount from quantity and rate."""
        self.amount = (self.quantity * self.rate).quantize(Decimal('0.01'))


class PaymentMethod(models.TextChoices):
    """Payment method choices."""
    CASH = 'CASH', 'Cash'
    CHECK = 'CHECK', 'Check'
    CARD = 'CARD', 'Credit Card'
    ACH = 'ACH', 'Bank Transfer'
    OTHER = 'OTHER', 'Other'


class InvoicePayment(models.Model):
    """
    Payment received on an invoice.
    
    Auto-posts to ledger:
      DR 1024 Payments to Deposit
      CR 1010 Accounts Receivable
    
    Later (Phase 2) gets matched to BankDeposit when money clears.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments',
        help_text="Invoice this payment is for"
    )
    
    # Jobber metadata
    jobber_payment_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Jobber payment ID (for deduplication)"
    )
    
    # Payment details
    payment_date = models.DateField(
        help_text="Date payment was received"
    )
    
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Payment amount"
    )
    
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Check number, last 4 of card, etc."
    )
    
    # Jobber specific fields
    jobber_paid_with = models.CharField(
        max_length=50,
        blank=True,
        help_text="Jobber payment method (e.g., 'visa', 'cash')"
    )
    
    jobber_paid_through = models.CharField(
        max_length=50,
        blank=True,
        help_text="Jobber payment processor (e.g., 'jobber_payments')"
    )
    
    # Ledger posting metadata
    journal_entry = models.ForeignKey(
        JournalEntryModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='forbes_lawn_accounting_invoice_payments',  # Changed to be unique
        help_text="Journal entry that posts payment to Payments to Deposit"
    )
    
    posted_to_ledger = models.BooleanField(
        default=False,
        help_text="Has this payment been posted to the ledger?"
    )
    
    posted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this payment was posted to ledger"
    )
    
    # Bank deposit tracking (Phase 2)
    cleared = models.BooleanField(
        default=False,
        help_text="Has this payment cleared the bank?"
    )
    
    cleared_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date payment cleared the bank"
    )
    
    # Sync metadata
    synced_at = models.DateTimeField(
        help_text="When this record was last synced from Jobber"
    )
    
    jobber_raw = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw JSON response from Jobber API"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'forbes_lawn_invoice_payment'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['invoice', 'payment_date']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['cleared', 'cleared_date']),
            models.Index(fields=['jobber_payment_id']),
        ]
        verbose_name = 'Invoice Payment'
        verbose_name_plural = 'Invoice Payments'
    
    def __str__(self):
        return f"${self.amount} on {self.payment_date} - {self.get_payment_method_display()}"


# ADD THIS TO forbes_lawn_accounting/models.py
# Place at the end of the file

class SalesTaxSummary(models.Model):
    """
    Monthly sales tax summary for Kansas DOR filing.
    Auto-calculated from invoices, uses Jobber tax amounts as source of truth.
    """
    
    entity = models.ForeignKey(
        EntityModel,
        on_delete=models.PROTECT,
        related_name='forbes_lawn_tax_summaries',
        help_text="Forbes Lawn Spraying LLC entity"
    )
    
    # Period
    month = models.DateField(
        help_text="First day of the month (e.g., 2026-01-01 for January 2026)",
        db_index=True
    )
    
    # Revenue breakdown (auto-calculated from invoices)
    total_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total invoice revenue for the month"
    )
    
    taxable_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Revenue from taxable services"
    )
    
    non_taxable_revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Revenue from non-taxable services (mowing, aeration, etc.)"
    )
    
    # Tax collected - FROM JOBBER (never recalculate!)
    tax_collected = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total tax from Jobber invoices - SOURCE OF TRUTH"
    )
    
    # Filing tracking
    filed = models.BooleanField(
        default=False,
        help_text="Has this month's tax been filed with Kansas DOR?"
    )
    
    filed_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date filed with Kansas DOR"
    )
    
    # Payment tracking
    payment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount paid to Kansas DOR"
    )
    
    payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date payment was made to Kansas DOR"
    )
    
    payment_confirmation = models.CharField(
        max_length=100,
        blank=True,
        help_text="Confirmation number from Kansas DOR"
    )
    
    # Notes
    notes = models.TextField(
        blank=True,
        help_text="Filing notes, adjustments, etc."
    )
    
    # Tracking
    last_calculated = models.DateTimeField(
        auto_now=True,
        help_text="When amounts were last recalculated from invoices"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'forbes_lawn_sales_tax_summary'
        ordering = ['-month']
        unique_together = [['entity', 'month']]
        indexes = [
            models.Index(fields=['entity', 'month']),
            models.Index(fields=['filed', 'month']),
        ]
        verbose_name = 'Sales Tax Summary'
        verbose_name_plural = 'Sales Tax Summaries'
    
    def __str__(self):
        return f"Sales Tax - {self.month.strftime('%B %Y')}"
    
    @property
    def due_date(self):
        """
        Kansas sales tax due on 25th of following month.
        e.g., December 2025 tax is due January 25, 2026
        """
        if self.month.month == 12:
            return self.month.replace(year=self.month.year + 1, month=1, day=25)
        else:
            return self.month.replace(month=self.month.month + 1, day=25)
    
    @property
    def is_overdue(self):
        """Is the filing overdue?"""
        if self.filed:
            return False
        return timezone.now().date() > self.due_date
    
    @property
    def is_due_soon(self):
        """Is filing due within 10 days?"""
        if self.filed:
            return False
        days_until = (self.due_date - timezone.now().date()).days
        return 0 <= days_until <= 10
    
    @property
    def days_until_due(self):
        """Days until due date (negative if overdue)"""
        return (self.due_date - timezone.now().date()).days
    
    def recalculate_from_invoices(self):
        """
        Recalculate tax summary from invoices.
        Uses Jobber tax amounts as source of truth - NO ROUNDING ISSUES!
        """
        from django.db.models import Sum, Q
        
        # Get all invoices for this month (exclude draft/void)
        invoices = Invoice.objects.filter(
            entity=self.entity,
            invoice_date__year=self.month.year,
            invoice_date__month=self.month.month
        ).exclude(
            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.VOID]
        )
        
        # Total revenue
        self.total_revenue = invoices.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0.00')
        
        # Taxable revenue (sum of taxable_subtotal from each invoice)
        self.taxable_revenue = invoices.aggregate(
            total=Sum('taxable_subtotal')
        )['total'] or Decimal('0.00')
        
        # Tax collected - DIRECTLY FROM JOBBER
        self.tax_collected = invoices.aggregate(
            total=Sum('tax_amount')
        )['total'] or Decimal('0.00')
        
        # Non-taxable is everything else
        self.non_taxable_revenue = invoices.aggregate(
            total=Sum('subtotal')
        )['total'] or Decimal('0.00')
        self.non_taxable_revenue -= self.taxable_revenue
        
        self.save()
        
        return self
    
    def mark_as_filed(self, filed_date=None, payment_amount=None, payment_date=None, confirmation=''):
        """Mark this month as filed with Kansas DOR"""
        self.filed = True
        self.filed_date = filed_date or timezone.now().date()
        
        if payment_amount:
            self.payment_amount = payment_amount
        if payment_date:
            self.payment_date = payment_date
        if confirmation:
            self.payment_confirmation = confirmation
        
        self.save()