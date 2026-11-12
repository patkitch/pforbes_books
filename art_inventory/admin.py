from django.contrib import admin
from .models import Artwork,InventoryActivity,Location,Original,PrintOption,PrintStock
admin.site.register(Artwork)
admin.site.register(Location)
admin.site.register(PrintStock)
@admin.register(Original)
class OriginalAdmin(admin.ModelAdmin):
    list_display=("sku","artwork","status","location","price","canvas_profile")
    list_filter=("status","location","canvas_profile")
    search_fields=("sku","artwork__title")
@admin.register(PrintOption)
class PrintOptionAdmin(admin.ModelAdmin):
    list_display=("sku","artwork","print_type","price","is_active")
    list_filter=("print_type","is_active")
    search_fields=("sku","artwork__title")
@admin.register(InventoryActivity)
class ActivityAdmin(admin.ModelAdmin):
    list_display=("activity_date","kind","original","print_option","quantity","source")
    list_filter=("kind","activity_date")
    readonly_fields=("created_at",)
