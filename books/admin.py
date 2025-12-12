from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from django_ledger.models import ItemModel, BillModel, InvoiceModel, PurchaseOrderModel, ItemTransactionModel, UnitOfMeasureModel, EntityUnitModel,ReceiptModel,TransactionModel, StagedTransactionModel, CustomerModel, VendorModel
from decimal import Decimal, InvalidOperation
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, F, Max
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from collections import defaultdict
from .models import AdminReports
import csv as csvlib



# --- Unregister ItemModel if already registered, then re-register with custom admin ---
try:
    admin.site.unregister(ItemModel)
except admin.sites.NotRegistered:
    pass

@admin.register(ItemModel)
class ItemModelAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "sku", "is_active", "created", "updated")
    search_fields = ("uuid", "name", "sku")
    list_filter = ("is_active",)
    ordering = ("-updated",)

def register_with_auto_columns(model):
    class AutoAdmin(admin.ModelAdmin):
        def get_list_display(self, request):
            names = []
            for f in model._meta.get_fields():
                if getattr(f, "concrete", False) and not f.many_to_many and not f.one_to_many:
                    names.append(f.name)
            return tuple(names[:8]) or ("pk",)
        ordering = ("-pk",)
    try:
        admin.site.register(model, AutoAdmin)
    except AlreadyRegistered:
        pass

# ItemModel is already registered by django-ledger in your setup; don't touch it.
register_with_auto_columns(BillModel)
register_with_auto_columns(InvoiceModel)
register_with_auto_columns(PurchaseOrderModel)
register_with_auto_columns(ItemTransactionModel)
register_with_auto_columns(UnitOfMeasureModel)
register_with_auto_columns(EntityUnitModel)
register_with_auto_columns(ReceiptModel)
register_with_auto_columns(TransactionModel)
register_with_auto_columns(StagedTransactionModel)
register_with_auto_columns(CustomerModel)
register_with_auto_columns(VendorModel)


# ---------- Inventory Valuation report ----------








# (Optional) admin action to apply discount math now and store the net on the bill or post a JE.
# You can read extras = bill.extras and do your logic here if/when you add posting hooks.