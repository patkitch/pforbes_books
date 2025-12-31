"""
Django Admin configuration for Forbes Lawn Accounting
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (Customer, ServiceItem, Invoice, InvoiceLine, InvoicePayment,)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """
    Admin interface for Customer model.
    Shows sync status, Jobber metadata, and addresses.
    """
    list_display = [
        'name',
        'company_name',
        'email',
        'phone',
        'active_status',
        'current_balance',
        'last_synced',
    ]
    
    list_filter = [
        'active',
        'entity',
        'synced_at',
    ]
    
    search_fields = [
        'name',
        'company_name',
        'email',
        'phone',
        'jobber_id',
        'billing_city',
        'service_city',
    ]
    
    readonly_fields = [
        'jobber_id',
        'jobber_client_id',
        'jobber_raw',
        'synced_at',
        'created_at',
        'updated_at',
        'ledger_customer_link',
        'current_balance',
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'entity',
                'name',
                'company_name',
                'email',
                'phone',
                'active',
            )
        }),
        ('Billing Address', {
            'fields': (
                'billing_address_line1',
                'billing_address_line2',
                'billing_city',
                'billing_state',
                'billing_zip',
            ),
            'classes': ('collapse',),
        }),
        ('Service Address', {
            'fields': (
                'service_address_line1',
                'service_address_line2',
                'service_city',
                'service_state',
                'service_zip',
            ),
            'classes': ('collapse',),
        }),
        ('Django Ledger Integration', {
            'fields': (
                'ledger_customer',
                'ledger_customer_link',
                'current_balance',
            ),
            'classes': ('collapse',),
        }),
        ('Jobber Sync Metadata', {
            'fields': (
                'jobber_id',
                'jobber_client_id',
                'synced_at',
                'jobber_raw',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def active_status(self, obj):
        """Display active status with color."""
        if obj.active:
            return format_html(
                '<span style="color: green;">●</span> Active'
            )
        return format_html(
            '<span style="color: red;">●</span> Inactive'
        )
    active_status.short_description = 'Status'
    
    def current_balance(self, obj):
        """Display current AR balance."""
        balance = obj.get_balance()
        if balance > 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">${}</span>',
                '${:,.2f}'.format(balance)
            )
        return format_html(
            '<span style="color: green;">${}</span>',
            '${:,.2f}'.format(balance)
        )
    current_balance.short_description = 'AR Balance'
    
    def last_synced(self, obj):
        """Display last sync time in friendly format."""
        if obj.synced_at:
            return obj.synced_at.strftime('%Y-%m-%d %H:%M')
        return '—'
    last_synced.short_description = 'Last Synced'
    
    def ledger_customer_link(self, obj):
        """Link to Django Ledger customer record."""
        if obj.ledger_customer:
            from django.urls import reverse
            url = reverse(
                'admin:django_ledger_customermodel_change',
                args=[obj.ledger_customer.pk]
            )
            return format_html(
                '<a href="{}" target="_blank">View Ledger Customer →</a>',
                url
            )
        return '—'
    ledger_customer_link.short_description = 'Ledger Customer'


@admin.register(ServiceItem)
class ServiceItemAdmin(admin.ModelAdmin):
    """
    Admin interface for ServiceItem model.
    Shows services synced from Jobber with pricing and revenue account mapping.
    """
    list_display = [
        'name',
        'category_name',
        'default_rate_display',
        'taxable_status',
        'revenue_account_display',
        'active_status',
        'last_synced',
    ]
    
    list_filter = [
        'active',
        'taxable',
        'entity',
        'category_name',
        'synced_at',
    ]
    
    search_fields = [
        'name',
        'description',
        'category_name',
        'jobber_id',
    ]
    
    readonly_fields = [
        'jobber_id',
        'jobber_raw',
        'synced_at',
        'created_at',
        'updated_at',
        'ledger_item_link',
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'entity',
                'name',
                'description',
                'category_name',
                'active',
            )
        }),
        ('Pricing & Tax', {
            'fields': (
                'default_rate',
                'taxable',
            )
        }),
        ('Revenue Account Mapping', {
            'fields': (
                'revenue_account',
            ),
            'description': '4024 for taxable services, 4025 for non-taxable services',
        }),
        ('Django Ledger Integration', {
            'fields': (
                'ledger_item',
                'ledger_item_link',
            ),
            'classes': ('collapse',),
        }),
        ('Jobber Sync Metadata', {
            'fields': (
                'jobber_id',
                'synced_at',
                'jobber_raw',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def default_rate_display(self, obj):
        """Display default rate as currency."""
        return "${:,.2f}".format(obj.default_rate)
    default_rate_display.short_description = 'Default Rate'
    default_rate_display.admin_order_field = 'default_rate'
    
    def taxable_status(self, obj):
        """Display taxable status with icon."""
        if obj.taxable:
            return format_html(
                '<span style="color: orange;">⚠</span> Taxable'
            )
        return format_html(
            '<span style="color: green;">✓</span> Non-Taxable'
        )
    taxable_status.short_description = 'Tax Status'
    
    def revenue_account_display(self, obj):
        """Display revenue account code and name."""
        if obj.revenue_account:
            return format_html(
                '<strong>{}</strong>: {}',
                obj.revenue_account.code,
                obj.revenue_account.name
            )
        return '—'
    revenue_account_display.short_description = 'Revenue Account'
    
    def active_status(self, obj):
        """Display active status with color."""
        if obj.active:
            return format_html(
                '<span style="color: green;">●</span> Active'
            )
        return format_html(
            '<span style="color: red;">●</span> Inactive'
        )
    active_status.short_description = 'Status'
    
    def last_synced(self, obj):
        """Display last sync time in friendly format."""
        if obj.synced_at:
            return obj.synced_at.strftime('%Y-%m-%d %H:%M')
        return '—'
    last_synced.short_description = 'Last Synced'
    
    def ledger_item_link(self, obj):
        """Link to Django Ledger item record."""
        if obj.ledger_item:
            from django.urls import reverse
            url = reverse(
                'admin:django_ledger_itemmodel_change',
                args=[obj.ledger_item.pk]
            )
            return format_html(
                '<a href="{}" target="_blank">View Ledger Item →</a>',
                url
            )
        return '—'
    ledger_item_link.short_description = 'Ledger Item'

# Add these imports to the top of admin.py:
# from .models import (
#     Customer,
#     ServiceItem,
#     Invoice,           # ADD
#     InvoiceLine,       # ADD
#     InvoicePayment,    # ADD
# )

# Then add these admin classes at the end of the file:

# ============================================================================
# INVOICE ADMIN CLASSES
# ============================================================================

class InvoiceLineInline(admin.TabularInline):
    """Inline display of invoice lines."""
    model = InvoiceLine
    extra = 0
    fields = [
        'line_number',
        'service_item',
        'description',
        'service_date',
        'quantity',
        'rate',
        'amount',
        'taxable',
    ]
    readonly_fields = ['amount']


class InvoicePaymentInline(admin.TabularInline):
    """Inline display of invoice payments."""
    model = InvoicePayment
    extra = 0
    fields = [
        'payment_date',
        'amount',
        'payment_method',
        'reference',
        'cleared',
        'cleared_date',
    ]
    readonly_fields = ['cleared', 'cleared_date']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """
    Admin interface for Invoice model.
    Shows invoice details with inline lines and payments.
    """
    list_display = [
        'invoice_number',
        'customer_link',
        'invoice_date',
        'total_display',
        'amount_paid_display',
        'balance_due_display',
        'status_display',
        'posted_status',
        'last_synced',
    ]
    
    list_filter = [
        'status',
        'posted_to_ledger',
        'entity',
        'invoice_date',
        'synced_at',
    ]
    
    search_fields = [
        'invoice_number',
        'customer__name',
        'jobber_invoice_id',
        'jobber_job_numbers',
    ]
    
    readonly_fields = [
        'jobber_invoice_id',
        'jobber_job_numbers',
        'subtotal',
        'taxable_subtotal',
        'tax_amount',
        'total',
        'amount_paid',
        'balance_due',
        'ar_journal_entry',
        'posted_to_ledger',
        'posted_at',
        'synced_at',
        'jobber_raw',
        'created_at',
        'updated_at',
        'ledger_journal_entry_link',
    ]
    
    fieldsets = (
        ('Invoice Details', {
            'fields': (
                'entity',
                'customer',
                'invoice_number',
                'invoice_date',
                'due_date',
                'status',
            )
        }),
        ('Amounts', {
            'fields': (
                'subtotal',
                'discount_amount',
                'taxable_subtotal',
                'tax_rate',
                'tax_amount',
                'total',
                'amount_paid',
                'balance_due',
            )
        }),
        ('Notes', {
            'fields': (
                'note_to_customer',
                'internal_notes',
            ),
            'classes': ('collapse',),
        }),
        ('Ledger Posting', {
            'fields': (
                'posted_to_ledger',
                'posted_at',
                'ar_journal_entry',
                'ledger_journal_entry_link',
            ),
            'classes': ('collapse',),
        }),
        ('Jobber Sync Metadata', {
            'fields': (
                'jobber_invoice_id',
                'jobber_job_numbers',
                'synced_at',
                'jobber_raw',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [InvoiceLineInline, InvoicePaymentInline]
    
    def customer_link(self, obj):
        """Link to customer."""
        from django.urls import reverse
        url = reverse('admin:forbes_lawn_accounting_customer_change', args=[obj.customer.pk])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'Customer'
    customer_link.admin_order_field = 'customer__name'
    
    def total_display(self, obj):
        """Display total as currency."""
        return format_html('<strong>${}</strong>', '${:,.2f}'.format(obj.total))
    total_display.short_description = 'Total'
    total_display.admin_order_field = 'total'
    
    def amount_paid_display(self, obj):
        """Display amount paid as currency."""
        if obj.amount_paid > 0:
            return format_html('<span style="color: green;">${}</span>', '${:,.2f}'.format(obj.amount_paid))
        return '$0.00'
    amount_paid_display.short_description = 'Paid'
    amount_paid_display.admin_order_field = 'amount_paid'
    
    def balance_due_display(self, obj):
        """Display balance due as currency."""
        if obj.balance_due > 0:
            return format_html('<span style="color: red; font-weight: bold;">${}</span>', '${:,.2f}'.format(obj.balance_due))
        return format_html('<span style="color: green;">$0.00</span>')
    balance_due_display.short_description = 'Balance'
    balance_due_display.admin_order_field = 'balance_due'
    
    def status_display(self, obj):
        """Display status with color."""
        colors = {
            'DRAFT': 'gray',
            'OPEN': 'orange',
            'PARTIAL': 'blue',
            'PAID': 'green',
            'VOID': 'red',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def posted_status(self, obj):
        """Display ledger posting status."""
        if obj.posted_to_ledger:
            return format_html('<span style="color: green;">✓ Posted</span>')
        return format_html('<span style="color: orange;">⧗ Not Posted</span>')
    posted_status.short_description = 'Ledger'
    posted_status.admin_order_field = 'posted_to_ledger'
    
    def last_synced(self, obj):
        """Display last sync time."""
        if obj.synced_at:
            return obj.synced_at.strftime('%Y-%m-%d %H:%M')
        return '—'
    last_synced.short_description = 'Last Synced'
    
    def ledger_journal_entry_link(self, obj):
        """Link to journal entry."""
        if obj.ar_journal_entry:
            from django.urls import reverse
            url = reverse(
                'admin:django_ledger_journalentrymodel_change',
                args=[obj.ar_journal_entry.pk]
            )
            return format_html('<a href="{}" target="_blank">View Journal Entry →</a>', url)
        return '—'
    ledger_journal_entry_link.short_description = 'Journal Entry'


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    """Admin interface for InvoiceLine model."""
    list_display = [
        'invoice_link',
        'line_number',
        'description',
        'service_date',
        'quantity',
        'rate',
        'amount_display',
        'taxable_display',
    ]
    
    list_filter = [
        'taxable',
        'service_date',
    ]
    
    search_fields = [
        'invoice__invoice_number',
        'invoice__customer__name',
        'description',
        'service_item__name',
    ]
    
    readonly_fields = ['amount', 'jobber_line_id']
    
    def invoice_link(self, obj):
        """Link to invoice."""
        from django.urls import reverse
        url = reverse('admin:forbes_lawn_accounting_invoice_change', args=[obj.invoice.pk])
        return format_html('<a href="{}">Invoice {}</a>', url, obj.invoice.invoice_number)
    invoice_link.short_description = 'Invoice'
    
    def amount_display(self, obj):
        """Display amount as currency."""
        return "${:,.2f}".format(obj.amount)
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def taxable_display(self, obj):
        """Display taxable status."""
        if obj.taxable:
            return format_html('<span style="color: orange;">⚠ Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    taxable_display.short_description = 'Taxable'


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    """Admin interface for InvoicePayment model."""
    list_display = [
        'invoice_link',
        'payment_date',
        'amount_display',
        'payment_method',
        'reference',
        'cleared_status',
        'posted_status',
    ]
    
    list_filter = [
        'payment_method',
        'cleared',
        'posted_to_ledger',
        'payment_date',
    ]
    
    search_fields = [
        'invoice__invoice_number',
        'invoice__customer__name',
        'reference',
        'jobber_payment_id',
    ]
    
    readonly_fields = [
        'jobber_payment_id',
        'jobber_paid_with',
        'jobber_paid_through',
        'journal_entry',
        'posted_to_ledger',
        'posted_at',
        'cleared',
        'cleared_date',
        'synced_at',
        'jobber_raw',
        'created_at',
        'ledger_journal_entry_link',
    ]
    
    fieldsets = (
        ('Payment Details', {
            'fields': (
                'invoice',
                'payment_date',
                'amount',
                'payment_method',
                'reference',
            )
        }),
        ('Bank Clearing', {
            'fields': (
                'cleared',
                'cleared_date',
            )
        }),
        ('Ledger Posting', {
            'fields': (
                'posted_to_ledger',
                'posted_at',
                'journal_entry',
                'ledger_journal_entry_link',
            ),
            'classes': ('collapse',),
        }),
        ('Jobber Sync Metadata', {
            'fields': (
                'jobber_payment_id',
                'jobber_paid_with',
                'jobber_paid_through',
                'synced_at',
                'jobber_raw',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def invoice_link(self, obj):
        """Link to invoice."""
        from django.urls import reverse
        url = reverse('admin:forbes_lawn_accounting_invoice_change', args=[obj.invoice.pk])
        return format_html(
            '<a href="{}">Invoice {} - {}</a>',
            url,
            obj.invoice.invoice_number,
            obj.invoice.customer.name
        )
    invoice_link.short_description = 'Invoice'
    
    def amount_display(self, obj):
        """Display amount as currency."""
        return format_html('<strong>${}</strong>', '${:,.2f}'.format(obj.amount))
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def cleared_status(self, obj):
        """Display cleared status."""
        if obj.cleared:
            return format_html(
                '<span style="color: green;">✓ Cleared {}</span>',
                obj.cleared_date.strftime('%m/%d/%y') if obj.cleared_date else ''
            )
        return format_html('<span style="color: orange;">⧗ Pending</span>')
    cleared_status.short_description = 'Bank Status'
    
    def posted_status(self, obj):
        """Display ledger posting status."""
        if obj.posted_to_ledger:
            return format_html('<span style="color: green;">✓ Posted</span>')
        return format_html('<span style="color: orange;">⧗ Not Posted</span>')
    posted_status.short_description = 'Ledger'
    
    def ledger_journal_entry_link(self, obj):
        """Link to journal entry."""
        if obj.journal_entry:
            from django.urls import reverse
            url = reverse(
                'admin:django_ledger_journalentrymodel_change',
                args=[obj.journal_entry.pk]
            )
            return format_html('<a href="{}" target="_blank">View Journal Entry →</a>', url)
        return '—'
    ledger_journal_entry_link.short_description = 'Journal Entry'