from decimal import Decimal
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Location,
    StockAllocation,
    StockTransfer,
    StatusOverlay,
    PendingReceipt,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(StockAllocation)
class StockAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "item_display",
        "location",
        "quantity",
        "status",
        "on_hand_display",
        "allocated_total_display",
        "unallocated_display",
        "updated",
    )
    list_filter = ("location", "status")
    search_fields = ("item__name", "item__sku", "location__name")
    autocomplete_fields = ("item", "location")
    readonly_fields = ("on_hand_readonly", "allocated_total_readonly", "unallocated_readonly")

    fieldsets = (
        (None, {
            "fields": (
                "item",
                "location",
                "quantity",
                "status",
                "note",
            )
        }),
        ("Django-Ledger (read-only)", {
            "classes": ("collapse",),
            "fields": ("on_hand_readonly", "allocated_total_readonly", "unallocated_readonly")
        }),
    )

    def item_display(self, obj):
        return f"{obj.item.name} ({obj.item.item_number or obj.item.uuid})"
    item_display.short_description = "Item"

    def on_hand_display(self, obj):
        return StockAllocation.on_hand_qty(obj.item)
    on_hand_display.short_description = "On hand (Ledger)"

    def allocated_total_display(self, obj):
        return StockAllocation.allocated_total(obj.item)
    allocated_total_display.short_description = "Allocated (all locations)"

    def unallocated_display(self, obj):
        return StockAllocation.unallocated_qty(obj.item)
    unallocated_display.short_description = "Unallocated"

    # read-only fields in form
    def on_hand_readonly(self, obj):
        if not obj or not obj.pk:
            return "-"
        return self.on_hand_display(obj)

    def allocated_total_readonly(self, obj):
        if not obj or not obj.pk:
            return "-"
        return self.allocated_total_display(obj)

    def unallocated_readonly(self, obj):
        if not obj or not obj.pk:
            return "-"
        return self.unallocated_display(obj)


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ("item_display", "from_location", "to_location", "quantity", "created", "requested_by")
    list_filter = ("from_location", "to_location")
    search_fields = ("item__name", "item__sku", "note")
    autocomplete_fields = ("item", "from_location", "to_location")
    date_hierarchy = "created"

    def item_display(self, obj):
        return f"{obj.item.name} ({obj.item.item_number or obj.item.uuid})"


@admin.register(StatusOverlay)
class StatusOverlayAdmin(admin.ModelAdmin):
    list_display = ("item_display", "location", "status", "effective", "note")
    list_filter = ("status", "location")
    search_fields = ("item__name", "item__sku", "note")
    autocomplete_fields = ("item", "location")

    def item_display(self, obj):
        return f"{obj.item.name} ({obj.item.item_number or obj.item.uuid})"


@admin.register(PendingReceipt)
class PendingReceiptAdmin(admin.ModelAdmin):
    list_display = ("item_display", "location", "expected_qty", "expected_date", "vendor_name", "po_or_bill_ref", "created")
    list_filter = ("location",)
    search_fields = ("item__name", "item__sku", "vendor_name", "po_or_bill_ref", "note")
    autocomplete_fields = ("item", "location")
    date_hierarchy = "created"

    def item_display(self, obj):
        return f"{obj.item.name} ({obj.item.item_number or obj.item.uuid})"

