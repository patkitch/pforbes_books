# forbes_lawn_billing/admin.py

from django.contrib import admin
from .models import Invoice, InvoiceLine, InvoicePayment, InvoiceAttachment


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    fields = ("line_number", "service_date", "item_name", "description",
              "quantity", "rate", "line_amount", "taxable", "jobber_line_id", "jobber_service_id",)
    readonly_fields = ("line_amount",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by("line_number", "id")


class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0

    # Use the NEW field names here:
    fields = (
        "payment_date",
        "amount",
        "payment_method",
        "jobber_type",
        "jobber_paid_with",
        "jobber_paid_through",
        "reference",
        "jobber_payment_id",
    )

    readonly_fields = (
        "jobber_type",
        "jobber_paid_with",
        "jobber_paid_through",
        "jobber_payment_id",
    )


class InvoiceAttachmentInline(admin.TabularInline):
    model = InvoiceAttachment
    extra = 0
    fields = ("file", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer_name",
        "customer",
        "entity",
        "invoice_date",
        "due_date",
        "status",
        "total",
        "amount_paid",
        "balance_due",
        "paid_in_full",
        "ar_journal_entry",
        
    )
    list_filter = ("status", "invoice_date", "due_date", "paid_in_full")
    search_fields = ("invoice_number", "customer_name", "customer__customer_name","customer__email",)
    date_hierarchy = "invoice_date"
    # Let Django give you a nice search box for CustomerModel
    # X remove this for now.
    #autocomplete_fields = ("customer",)

    inlines = [InvoiceLineInline, InvoicePaymentInline, InvoiceAttachmentInline]

    readonly_fields = (
        "subtotal",
        "discount_amount",
        "taxable_subtotal",
        "tax_amount",
        "total",
        "amount_paid",
        "balance_due",
        "paid_in_full",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Invoice Header", {
            "fields": (
                "entity",
                "customer_name",
                "customer",
                "invoice_number",
                "status",
                "terms",
                "invoice_date",
                "due_date",
            )
        }),
        ("Contact & Addresses", {
            "fields": (
                "email_to", "email_cc", "email_bcc",
                "bill_to_name", "bill_to_line1", "bill_to_line2",
                "bill_to_city", "bill_to_state", "bill_to_zip", "bill_to_country",
            )
        }),
        
        
        ("Notes", {
            "fields": (
                "tags",
                "payment_instructions",
                "note_to_customer",
                "memo_on_statement",
            )
        }),
        ("Totals & Tax", {
            "fields": (
                "subtotal",
                "discount_percent",
                "discount_amount",
                "taxable_subtotal",
                "tax_rate_name",
                "tax_rate_percent",
                "tax_amount",
                "total",
                "deposit_amount",
                "amount_paid",
                "balance_due",
                "paid_in_full",
            )
        }),
        ("Jobber Data", {
            "classes": ("collapse",),  # <-- collapsible
            "fields": (
                "jobber_invoice_id",
                "jobber_client_id",
                "jobber_property_id",
            ),
        }),
        ("Audit", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    def save_related(self, request, form, formsets, change):
        """
        After saving inlines (lines/payments), recompute invoice totals so
        the summary on the right behaves like QuickBooks.
        """
        super().save_related(request, form, formsets, change)
        invoice = form.instance
        invoice.recompute_totals_from_lines()
        invoice.save()

@admin.register(InvoicePayment)
class InvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "payment_date", "amount","payment_method")