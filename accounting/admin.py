# accounting/admin.py
from django.contrib import admin
from .models import BillPayment

@admin.register(BillPayment)
class BillPaymentAdmin(admin.ModelAdmin):
    list_display = ("id","bill","vendor","date","amount","discount_taken","method","reference","created_at")
    search_fields = ("reference",)
    list_filter = ("method","date")
