"""
Forbes Lawn Accounting - Django Admin Configuration
Includes link back to the beautiful dashboard!
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from forbes_lawn_accounting.models import (
    Customer,
    ServiceItem,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    SalesTaxSummary
)


# Add custom admin site header with dashboard link
admin.site.site_header = "Forbes Lawn Accounting Admin"
admin.site.site_title = "Forbes Lawn Admin"
admin.site.index_title = format_html(
    'Welcome to Forbes Lawn Accounting Admin<br>'
    '<a href="/forbes-lawn/" style="color: #4a90e2; font-size: 14px; margin-top: 10px; display: inline-block;">'
    '🎨 View Dashboard →'
    '</a>'
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'active', 'synced_at']
    list_filter = ['active', 'entity']
    search_fields = ['name', 'email', 'jobber_client_id']
    readonly_fields = ['jobber_client_id', 'synced_at', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('entity', 'name', 'company_name', 'email', 'phone')
        }),
        ('Addresses', {
            'fields': (
                ('billing_address_line1', 'billing_address_line2'),
                ('billing_city', 'billing_state', 'billing_zip'),
                ('service_address_line1', 'service_address_line2'),
                ('service_city', 'service_state', 'service_zip'),
            )
        }),
        ('Status', {
            'fields': ('active',)
        }),
        ('Jobber Sync', {
            'fields': ('jobber_client_id', 'ledger_customer', 'synced_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ServiceItem)
class ServiceItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category_name', 'default_rate', 'taxable', 'active']
    list_filter = ['active', 'taxable', 'category_name']
    search_fields = ['name', 'description', 'jobber_id']
    readonly_fields = ['jobber_id', 'synced_at']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'invoice_date', 'total', 'balance_due', 'status']
    list_filter = ['status', 'invoice_date', 'entity']
    search_fields = ['invoice_number', 'customer__name', 'jobber_invoice_id']
    readonly_fields = ['jobber_invoice_id', 'synced_at', 'created_at', 'updated_at']
    date_hierarchy = 'invoice_date'
    
    fieldsets = (
        ('Invoice Info', {
            'fields': ('entity', 'customer', 'invoice_number', 'invoice_date', 'due_date')
        }),
        ('Amounts', {
            'fields': ('subtotal', 'taxable_subtotal', 'tax_rate', 'tax_amount', 'total', 'amount_paid', 'balance_due')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Notes', {
            'fields': ('internal_notes', 'note_to_customer'),
            'classes': ('collapse',)
        }),
        ('Jobber Sync', {
            'fields': ('jobber_invoice_id', 'synced_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'line_number', 'description', 'quantity', 'rate', 'amount', 'taxable']
    list_filter = ['taxable', 'invoice__invoice_date']
    search_fields = ['description', 'invoice__invoice_number']


@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'payment_date', 'amount', 'payment_method', 'posted_to_ledger']
    list_filter = ['payment_method', 'posted_to_ledger', 'cleared']
    search_fields = ['invoice__invoice_number', 'reference', 'jobber_payment_id']
    date_hierarchy = 'payment_date'
    readonly_fields = ['jobber_payment_id', 'synced_at', 'created_at']


@admin.register(SalesTaxSummary)
class SalesTaxSummaryAdmin(admin.ModelAdmin):
    list_display = ['month', 'total_revenue', 'tax_collected', 'filed', 'due_date_display', 'status_display']
    list_filter = ['filed', 'month']
    readonly_fields = ['last_calculated', 'created_at', 'updated_at', 'due_date']
    date_hierarchy = 'month'
    
    fieldsets = (
        ('Period', {
            'fields': ('entity', 'month')
        }),
        ('Revenue Breakdown', {
            'fields': ('total_revenue', 'taxable_revenue', 'non_taxable_revenue', 'tax_collected')
        }),
        ('Filing Status', {
            'fields': ('filed', 'filed_date', 'payment_amount', 'payment_date', 'payment_confirmation')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('due_date', 'last_calculated', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def due_date_display(self, obj):
        return obj.due_date.strftime('%B %d, %Y')
    due_date_display.short_description = 'Due Date'
    
    def status_display(self, obj):
        if obj.filed:
            return format_html('<span style="color: green;">✓ Filed</span>')
        elif obj.is_overdue:
            return format_html('<span style="color: red;">⚠️ OVERDUE</span>')
        elif obj.is_due_soon:
            return format_html('<span style="color: orange;">⏰ Due Soon</span>')
        else:
            return format_html('<span style="color: gray;">Pending</span>')
    status_display.short_description = 'Status'
    
    actions = ['recalculate_selected']
    
    def recalculate_selected(self, request, queryset):
        for summary in queryset:
            summary.recalculate_from_invoices()
        self.message_user(request, f"Recalculated {queryset.count()} tax summaries from invoices.")
    recalculate_selected.short_description = "Recalculate from invoices"