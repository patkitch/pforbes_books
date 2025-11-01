# books/admin.py  (or wherever your custom admin report views live)

from django.contrib import admin
from django.urls import path
from django.http import HttpResponse
from django.db.models import (
    Sum,
    F,
    DecimalField,
    FloatField,
    ExpressionWrapper,
    Value,
    OuterRef,
    Subquery,
    Q,
)
from django.db.models.functions import Coalesce

from django_ledger.models import ItemModel, ItemTransactionModel  # adjust import if needed


def inventory_sync_view(request):
    """
    CSV export that shows, per ItemModel:
    - What ItemModel says we've received (inventory_received / inventory_received_value)
    - What ItemTransactionModel history says is actually on hand
    - The difference between those two
    - Dollar impact of that difference

    Goal: find items where invoices show 0 available even though you've already received stock.
    """

    # --- 1. Build subqueries that aggregate ItemTransactionModel per item_model ---

    # Qty received = sum of quantities on BILL lines (incoming inventory)
    qty_received_tx_subq = (
        ItemTransactionModel.objects
        .filter(item_model=OuterRef('pk'), bill_model__isnull=False)
        .values('item_model')
        .annotate(total_qty=Coalesce(Sum('quantity'), 0.0))
        .values('total_qty')
    )

    # Qty sold = sum of quantities on INVOICE lines (outgoing / sold)
    qty_sold_tx_subq = (
        ItemTransactionModel.objects
        .filter(item_model=OuterRef('pk'), invoice_model__isnull=False)
        .values('item_model')
        .annotate(total_qty=Coalesce(Sum('quantity'), 0.0))
        .values('total_qty')
    )

    # Cost received from bills (money you spent acquiring this inventory)
    cost_received_tx_subq = (
        ItemTransactionModel.objects
        .filter(item_model=OuterRef('pk'), bill_model__isnull=False)
        .values('item_model')
        .annotate(total_cost=Coalesce(Sum('total_amount'), 0))
        .values('total_cost')
    )

    # Revenue from invoices (optional context, not used in diff math, but useful to see)
    revenue_invoiced_tx_subq = (
        ItemTransactionModel.objects
        .filter(item_model=OuterRef('pk'), invoice_model__isnull=False)
        .values('item_model')
        .annotate(total_rev=Coalesce(Sum('total_amount'), 0))
        .values('total_rev')
    )

    # --- 2. Annotate ItemModel with those numbers ---

    qs = (
        ItemModel.objects
        .annotate(
            qty_received_tx=Coalesce(
                Subquery(qty_received_tx_subq, output_field=FloatField()),
                0.0
            ),
            qty_sold_tx=Coalesce(
                Subquery(qty_sold_tx_subq, output_field=FloatField()),
                0.0
            ),
            cost_received_tx=Coalesce(
                Subquery(cost_received_tx_subq, output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(0)
            ),
            revenue_invoiced_tx=Coalesce(
                Subquery(revenue_invoiced_tx_subq, output_field=DecimalField(max_digits=20, decimal_places=2)),
                Value(0)
            ),
        )
        .annotate(
            qty_onhand_tx=ExpressionWrapper(
                F('qty_received_tx') - F('qty_sold_tx'),
                output_field=FloatField()
            ),

            # What the ItemModel itself is storing (your manual truth right now)
            qty_itemmodel_recorded=Coalesce(
                F('inventory_received'),
                Value(0.0),
                output_field=DecimalField(max_digits=20, decimal_places=3)
            ),

            # Compare transaction math vs ItemModel field:
            qty_difference=ExpressionWrapper(
                F('qty_onhand_tx') - F('qty_itemmodel_recorded'),
                output_field=FloatField()
            ),

            # Dollar impact of that diff at your set default_amount per unit
            dollar_impact=ExpressionWrapper(
                (F('qty_onhand_tx') - F('qty_itemmodel_recorded')) * F('default_amount'),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
        )
        .values(
            'uuid',
            'item_number',
            'name',
            'default_amount',
            'inventory_received',
            'inventory_received_value',
            'qty_received_tx',
            'qty_sold_tx',
            'qty_onhand_tx',
            'qty_itemmodel_recorded',
            'qty_difference',
            'dollar_impact',
        )
        .order_by('item_number', 'name')
    )

    # --- 3. Build CSV response ---
    import csv
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename=inventory_sync_report.csv'

    writer = csv.writer(resp)

    writer.writerow([
        'Item UUID',
        'Item Number',
        'Name',

        'Default Unit Cost (default_amount)',

        'ItemModel.inventory_received (qty lifetime)',
        'ItemModel.inventory_received_value ($ lifetime)',

        'Tx qty_received_from_bills',
        'Tx qty_sold_on_invoices',
        'Tx qty_onhand (received - sold)',

        'Recorded qty in ItemModel (inventory_received)',
        'Difference (TxOnHand - ItemModelReceived)',
        'Dollar Impact of Difference',
    ])

    for row in qs:
        writer.writerow([
            row.get('uuid', ''),
            row.get('item_number', ''),
            row.get('name', ''),

            row.get('default_amount', ''),

            row.get('inventory_received', ''),
            row.get('inventory_received_value', ''),

            row.get('qty_received_tx', ''),
            row.get('qty_sold_tx', ''),
            row.get('qty_onhand_tx', ''),

            row.get('qty_itemmodel_recorded', ''),
            row.get('qty_difference', ''),
            row.get('dollar_impact', ''),
        ])

    return resp


# --- 4. Wire this into admin URLs ---
# If you already have a custom AdminSite subclass with get_urls(), just
# add this path(...) to that list. If you don't, here's a mixin you can apply.

class InventoryAdminSiteMixin:
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'django_ledger/adminreports/inventory-sync/',
                self.admin_view(inventory_sync_view),
                name='inventory-sync-report'
            ),
        ]
        return custom_urls + urls

# If you already have something similar for 'inventory-valuation', keep that too.
# Just make sure both paths are returned in get_urls().
