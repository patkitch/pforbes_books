# reports/views_itx.py
from decimal import Decimal
from django.http import HttpResponse
from django.utils.encoding import smart_str
from django.contrib.admin.views.decorators import staff_member_required

from django_ledger.models import EntityModel
from django_ledger.views.mixins import DjangoLedgerSecurityMixIn
from django_ledger.models.items import ItemTransactionModel

from django.views.generic import DetailView
from django.urls import reverse

import csv

# ---- Admin landing pages (show a "Download CSV" button) ----

class ITxSnapshotPage(DjangoLedgerSecurityMixIn, DetailView):
    template_name = "admin/reports/itx_snapshot.html"
    slug_url_kwarg = "entity_slug"

    def get_queryset(self):
        # Used only to resolve the entity by slug with permission checks
        if not self.queryset:
            self.queryset = EntityModel.objects.for_user(user_model=self.request.user)
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "ITx On-Hand Snapshot"
        ctx["header_title"] = "ITx On-Hand Snapshot"
        ctx["download_url_name"] = "adminreports-itx-snapshot-csv"
        return ctx


class ITxTxDetailPage(DjangoLedgerSecurityMixIn, DetailView):
    template_name = "admin/reports/itx_tx_detail.html"
    slug_url_kwarg = "entity_slug"

    def get_queryset(self):
        if not self.queryset:
            self.queryset = EntityModel.objects.for_user(user_model=self.request.user)
        return super().get_queryset()

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "ITx Transaction Detail"
        ctx["header_title"] = "ITx Transaction Detail"
        ctx["download_url_name"] = "adminreports-itx-tx-detail-csv"
        return ctx


# ---- CSV download endpoints ----

@staff_member_required
def itx_snapshot_csv(request, entity_slug):
    entity = EntityModel.objects.for_user(user_model=request.user).get(slug=entity_slug)

    # Use the ledger’s own aggregate to respect received − sold ± any adjustments
    agg = ItemTransactionModel.objects.inventory_count(entity_model=entity)

    # CSV
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{smart_str(entity.slug)}_itx_onhand_snapshot.csv"'
    w = csv.writer(resp)
    w.writerow([
        "item_uuid", "item_number", "item_name", "sku", "uom",
        "qty_received", "cost_received",
        "qty_invoiced", "revenue_invoiced",
        "qty_onhand", "avg_cost", "value_onhand",
    ])

    for (item_id, item_number, item_name, sku, uom), vals in agg.items():
        w.writerow([
            item_id, item_number, item_name, sku, uom,
            _d(vals.get("received", 0)),
            _d(vals.get("received_value", 0)),
            _d(vals.get("sold", 0)),
            _d(vals.get("revenue_sold", 0)),
            _d(vals.get("on_hand", 0)),
            _d(vals.get("avg_cost", 0)),
            _d(vals.get("value_on_hand", 0)),
        ])
    return resp


@staff_member_required
def itx_tx_detail_csv(request, entity_slug):
    entity = EntityModel.objects.for_user(user_model=request.user).get(slug=entity_slug)

    qs = (
        ItemTransactionModel.objects
        .filter(item_model__entity_id=entity.uuid)
        .select_related(
            "item_model",
            "po_model", "bill_model", "invoice_model",
            "entity_unit",
        )
        .order_by("created")
    )

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{smart_str(entity.slug)}_itx_transactions.csv"'
    w = csv.writer(resp)
    w.writerow([
        "tx_uuid", "created",
        "item_uuid", "item_number", "item_name", "sku", "uom",
        "po_number", "bill_number", "invoice_number",
        "po_item_status", "entity_unit",
        "quantity", "po_unit_cost", "bill_unit_cost", "total_amount",
        "notes",
    ])

    for tx in qs:
        item = tx.item_model
        # Be defensive with attribute names and types
        qty = _d(getattr(tx, "quantity", 0))
        po_uc = _d(getattr(tx, "po_unit_cost", None))
        bill_uc = _d(getattr(tx, "unit_cost", None) or getattr(tx, "cost_per_unit", None))
        total = _d(getattr(tx, "total_amount", None) or (qty * (bill_uc or po_uc or Decimal("0"))))

        w.writerow([
            str(tx.uuid), getattr(tx, "created", ""),
            str(item.uuid) if item else "", getattr(item, "item_number", ""), getattr(item, "item_name", ""),
            getattr(item, "sku", ""), getattr(item, "uom", ""),
            getattr(getattr(tx, "po_model", None), "po_number", ""),
            getattr(getattr(tx, "bill_model", None), "bill_number", ""),
            getattr(getattr(tx, "invoice_model", None), "invoice_number", ""),
            getattr(tx, "po_item_status", ""),
            getattr(getattr(tx, "entity_unit", None), "name", ""),
            qty, po_uc, bill_uc, total,
            (getattr(tx, "desc", None) or getattr(tx, "description", "") or ""),
        ])
    return resp


def _d(value, places=3):
    """
    Safe decimal formatting helper: normalizes floats/None to Decimal and returns
    a plain number (string coercion handled by csv.writer).
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, float):
        value = Decimal(str(value))
    try:
        return value.quantize(Decimal("0.001")) if isinstance(value, Decimal) else value
    except Exception:
        return value
