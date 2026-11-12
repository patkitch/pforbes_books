from django.contrib import admin
from .models import Artwork,InventoryActivity,Location,Original,PrintOption,PrintStock
admin.site.register(Artwork)
admin.site.register(Location)
admin.site.register(PrintStock)
@admin.register(Original)
class OriginalAdmin(admin.ModelAdmin):
    list_display=("sku","artwork","status","location","price","listing_status")
    list_filter=("status","listing_status","location")
    search_fields=("sku","artwork__title")
@admin.register(PrintOption)
class PrintOptionAdmin(admin.ModelAdmin):
    list_display=("sku","artwork","label","is_active","listing_status")
    search_fields=("sku","artwork__title","label")
@admin.register(InventoryActivity)
class ActivityAdmin(admin.ModelAdmin):
    list_display=("activity_date","kind","original","print_option","quantity","source")
    list_filter=("kind","activity_date")
    readonly_fields=("created_at",)
