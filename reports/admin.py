from decimal import Decimal, InvalidOperation
import csv

from django.contrib import admin
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _

from .models import InventoryReconciliationReport

from django_ledger.models import EntityModel, ItemModel, ItemTransactionModel


@admin.register(InventoryReconciliationReport)
class InventoryReconciliationAdmin(admin.ModelAdmin):
    """
    Admin shell for the Inventory Reconciliation report.

    - Shows up under Reports in sidebar
    - Renders a custom page instead of trying to query a DB table
    - Offers a CSV download route
    """

    change_list_template = "admin/reports/inventory_reconciliation_changelist.html"

    #
    # 1. Override changelist_view so Django DOES NOT try to query this as a real DB model.
    #
    def changelist_view(self, request, extra_context=None):
        """
        Instead of letting ModelAdmin build a ChangeList (which queries the DB
        for this "model"), we manually render our custom template.
        """
        # Build any extra context we want on the page (like the download URL)
        context = {
            **self.admin_site.each_context(request),
            "title": "Inventory Reconciliation",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "download_url_name": "admin:inventory_reconciliation_download_csv",
        }

        if extra_context:
            context.update(extra_context)

        return TemplateResponse(
            request,
            self.change_list_template,
            context,
        )

    def get_urls(self):
        """
        Add custom admin URLs under this 'model' in the admin.
        """
        urls = super().get_urls()
        custom_urls = [
            path(
                "download-csv/",
                self.admin_site.admin_view(self.download_csv_view),
                name="inventory_reconciliation_download_csv",
            ),
        ]
        return custom_urls + urls

    def _get_authorized_entity(self, request):
        """
        Pick the entity the current user is allowed to work with.

        For now:
        - Take the first entity visible to this user.
        """
        qs = EntityModel.objects.for_user(user_model=request.user)
        return qs.first()

    def download_csv_view(self, request):
        """
        Build and return the reconciliation CSV.
        """
        entity = self._get_authorized_entity(request)
        if entity is None:
            resp = HttpResponse(
                "No entity available for this user.",
                content_type="text/plain",
            )
            resp["Content-Disposition"] = 'attachment; filename="inventory_reconciliation_ERROR.txt"'
            return resp

        # 1. Roll up transaction history per item
        txn_rollup_qs = ItemTransactionModel.objects.inventory_count(
            entity_model=entity
        )

        txn_rollup_map = {}
        for row in txn_rollup_qs:
            item_id = row.get("item_model_id")
            if not item_id:
                continue
            txn_rollup_map[item_id] = {
                "item_model__name": row.get("item_model__name"),
                "uom_name": row.get("item_model__uom__name"),

                "quantity_received": row.get("quantity_received") or Decimal("0"),
                "cost_received": row.get("cost_received") or Decimal("0"),

                "quantity_invoiced": row.get("quantity_invoiced") or Decimal("0"),
                "revenue_invoiced": row.get("revenue_invoiced") or Decimal("0"),

                "quantity_onhand": row.get("quantity_onhand") or Decimal("0"),

                "cost_average": row.get("cost_average") or Decimal("0"),
                "value_onhand": row.get("value_onhand") or Decimal("0"),
            }

        # 2. Pull the ItemModel "snapshot" for the same entity
        item_qs = ItemModel.objects.for_entity(entity_model=entity).select_related("uom")

        # 3. Build CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="inventory_reconciliation.csv"'

        writer = csv.writer(response)

        # Header row
        writer.writerow([
            "item_uuid",
            "item_number",
            "item_name",
            "sku",
            "uom",

            "inventory_received_model",
            "inventory_received_value_model",
            "avg_cost_model",

            "qty_received_txn",
            "cost_received_txn",
            "qty_sold_txn",
            "revenue_sold_txn",

            "qty_onhand_txn",
            "avg_cost_txn",
            "value_onhand_txn",

            "delta_received_qty",
            "delta_received_value",
        ])

        # Rows
        for item in item_qs:
            inv_recv_model = item.inventory_received or Decimal("0")
            inv_recv_val_model = item.inventory_received_value or Decimal("0")

            try:
                if inv_recv_model and inv_recv_model != 0:
                    avg_cost_model = inv_recv_val_model / inv_recv_model
                else:
                    avg_cost_model = Decimal("0")
            except (InvalidOperation, ZeroDivisionError):
                avg_cost_model = Decimal("0")

            roll = txn_rollup_map.get(item.uuid)

            if roll is None:
                qty_received_txn = Decimal("0")
                cost_received_txn = Decimal("0")
                qty_sold_txn = Decimal("0")
                revenue_sold_txn = Decimal("0")
                qty_onhand_txn = Decimal("0")
                avg_cost_txn = Decimal("0")
                value_onhand_txn = Decimal("0")
                uom_name = getattr(item.uom, "name", "")
                item_name = item.name
            else:
                qty_received_txn = roll["quantity_received"] or Decimal("0")
                cost_received_txn = roll["cost_received"] or Decimal("0")
                qty_sold_txn = roll["quantity_invoiced"] or Decimal("0")
                revenue_sold_txn = roll["revenue_invoiced"] or Decimal("0")
                qty_onhand_txn = roll["quantity_onhand"] or Decimal("0")
                avg_cost_txn = roll["cost_average"] or Decimal("0")
                value_onhand_txn = roll["value_onhand"] or Decimal("0")
                uom_name = roll["uom_name"] or getattr(item.uom, "name", "")
                item_name = roll["item_model__name"] or item.name

            delta_received_qty = qty_received_txn - (inv_recv_model or Decimal("0"))
            delta_received_value = cost_received_txn - (inv_recv_val_model or Decimal("0"))

            writer.writerow([
                str(item.uuid),
                item.item_number,
                item_name,
                item.sku or "",
                uom_name or "",

                str(inv_recv_model),
                str(inv_recv_val_model),
                str(round(avg_cost_model, 4)),

                str(qty_received_txn),
                str(cost_received_txn),
                str(qty_sold_txn),
                str(revenue_sold_txn),

                str(qty_onhand_txn),
                str(avg_cost_txn),
                str(value_onhand_txn),

                str(delta_received_qty),
                str(delta_received_value),
            ])

        return response

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
