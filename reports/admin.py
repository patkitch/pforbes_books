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

    - Appears under 'Reports' in the admin sidebar
    - Renders a custom page (not a normal changelist for a DB model)
    - Offers CSV download
    """

    change_list_template = "admin/reports/inventory_reconciliation_changelist.html"

    #
    # Utility: find which Entity the current user is allowed to see
    #
    def _get_authorized_entity(self, request):
        qs = EntityModel.objects.for_user(user_model=request.user)
        return qs.first()

    #
    # Core reconciliation logic:
    # build a list of per-item dicts that compare ItemModel vs ItemTransaction rollups
    #
    def _build_reconciliation_rows(self, entity):
        """
        Returns a list[dict] where each dict represents one item,
        including:
        - snapshot numbers from ItemModel
        - activity totals from ItemTransactionModel.inventory_count()
        - deltas
        """
        rows_out = []

        # 1. Query transaction rollup (what actually happened)
        txn_rollup_qs = ItemTransactionModel.objects.inventory_count(
            entity_model=entity
        )

        # Build a lookup map keyed by ItemModel UUID
        txn_rollup_map = {}
        for row in txn_rollup_qs:
            item_id = row.get("item_model_id")
            if not item_id:
                continue
            txn_rollup_map[item_id] = {
                "item_name": row.get("item_model__name"),
                "uom_name": row.get("item_model__uom__name"),

                "qty_received_txn": row.get("quantity_received") or Decimal("0"),
                "cost_received_txn": row.get("cost_received") or Decimal("0"),

                "qty_sold_txn": row.get("quantity_invoiced") or Decimal("0"),
                "revenue_sold_txn": row.get("revenue_invoiced") or Decimal("0"),

                "qty_onhand_txn": row.get("quantity_onhand") or Decimal("0"),

                "avg_cost_txn": row.get("cost_average") or Decimal("0"),
                "value_onhand_txn": row.get("value_onhand") or Decimal("0"),
            }

        # 2. Pull each ItemModel for that entity (what the system "thinks" you have)
        item_qs = ItemModel.objects.for_entity(entity_model=entity).select_related("uom")

        # 3. Merge the two worlds
        for item in item_qs:
            inv_recv_model = item.inventory_received or Decimal("0")
            inv_recv_val_model = item.inventory_received_value or Decimal("0")

            # model avg cost (snapshot)
            try:
                if inv_recv_model and inv_recv_model != 0:
                    avg_cost_model = inv_recv_val_model / inv_recv_model
                else:
                    avg_cost_model = Decimal("0")
            except (InvalidOperation, ZeroDivisionError):
                avg_cost_model = Decimal("0")

            roll = txn_rollup_map.get(item.uuid)

            if roll is None:
                # item exists in ItemModel but has no transaction history
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
                qty_received_txn = roll["qty_received_txn"]
                cost_received_txn = roll["cost_received_txn"]
                qty_sold_txn = roll["qty_sold_txn"]
                revenue_sold_txn = roll["revenue_sold_txn"]
                qty_onhand_txn = roll["qty_onhand_txn"]
                avg_cost_txn = roll["avg_cost_txn"]
                value_onhand_txn = roll["value_onhand_txn"]
                uom_name = roll["uom_name"] or getattr(item.uom, "name", "")
                item_name = roll["item_name"] or item.name

            delta_received_qty = qty_received_txn - inv_recv_model
            delta_received_value = cost_received_txn - inv_recv_val_model

            rows_out.append({
                "item_uuid": str(item.uuid),
                "item_number": item.item_number,
                "item_name": item_name,
                "sku": item.sku or "",
                "uom": uom_name or "",

                "inventory_received_model": inv_recv_model,
                "inventory_received_value_model": inv_recv_val_model,
                "avg_cost_model": round(avg_cost_model, 4),

                "qty_received_txn": qty_received_txn,
                "cost_received_txn": cost_received_txn,
                "qty_sold_txn": qty_sold_txn,
                "revenue_sold_txn": revenue_sold_txn,

                "qty_onhand_txn": qty_onhand_txn,
                "avg_cost_txn": avg_cost_txn,
                "value_onhand_txn": value_onhand_txn,

                "delta_received_qty": delta_received_qty,
                "delta_received_value": delta_received_value,
            })

        return rows_out

    #
    # 1. Override changelist_view so Django doesn't try to query a table.
    #    We build context ourselves.
    #
    def changelist_view(self, request, extra_context=None):
        entity = self._get_authorized_entity(request)
        rows = []
        no_entity_message = None

        if entity is None:
            no_entity_message = "No entity available for this user. Cannot build reconciliation."
        else:
            rows = self._build_reconciliation_rows(entity)

        context = {
            **self.admin_site.each_context(request),
            "title": "Inventory Reconciliation",
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "download_url_name": "admin:inventory_reconciliation_download_csv",
            "rows": rows,  # <- rows we just built
            "no_entity_message": no_entity_message,
        }

        if extra_context:
            context.update(extra_context)

        return TemplateResponse(
            request,
            self.change_list_template,
            context,
        )

    #
    # 2. Add the /download-csv/ route
    #
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "download-csv/",
                self.admin_site.admin_view(self.download_csv_view),
                name="inventory_reconciliation_download_csv",
            ),
        ]
        return custom_urls + urls

    #
    # 3. CSV download view
    #
    def download_csv_view(self, request):
        entity = self._get_authorized_entity(request)
        if entity is None:
            resp = HttpResponse(
                "No entity available for this user.",
                content_type="text/plain",
            )
            resp["Content-Disposition"] = 'attachment; filename="inventory_reconciliation_ERROR.txt"'
            return resp

        rows = self._build_reconciliation_rows(entity)

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

        # Data rows
        for r in rows:
            writer.writerow([
                r["item_uuid"],
                r["item_number"],
                r["item_name"],
                r["sku"],
                r["uom"],

                str(r["inventory_received_model"]),
                str(r["inventory_received_value_model"]),
                str(r["avg_cost_model"]),

                str(r["qty_received_txn"]),
                str(r["cost_received_txn"]),
                str(r["qty_sold_txn"]),
                str(r["revenue_sold_txn"]),

                str(r["qty_onhand_txn"]),
                str(r["avg_cost_txn"]),
                str(r["value_onhand_txn"]),

                str(r["delta_received_qty"]),
                str(r["delta_received_value"]),
            ])

        return response

    #
    # Permissions (read-only report)
    #
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
