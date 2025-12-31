from django.contrib import admin
from .models import SystemTask, BusinessTask

# We'll hook this up later:
# @admin.register(Task)
# class TaskAdmin(admin.ModelAdmin):
#     list_display = ("title", "is_done", "due_date", "created_at")
#     list_filter = ("is_done",)
#     search_fields = ("title", "notes")
@admin.register(SystemTask)
class SystemTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "status", "owner", "due_date", "created_at")
    list_filter = ("priority", "status", "owner")
    search_fields = ("title", "notes", "owner")
    ordering = ("-priority", "due_date", "status", "-created_at")


@admin.register(BusinessTask)
class BusinessTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "status", "owner", "due_date", "created_at")
    list_filter = ("priority", "status", "owner")
    search_fields = ("title", "notes", "owner")
    ordering = ("-priority", "due_date", "status", "-created_at")