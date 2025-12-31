from decimal import Decimal

from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce

from django_ledger.models import ItemModel, ItemTransactionModel


def get_inventory_items():
    """
    Returns the queryset of inventory items that InventoryGuardian should check.

    We assume:
    - for_inventory=True means this item is tracked as inventory.
    - is_active=True means item is currently in use.

    Adjust filters later if your business rules change.
    """
    return ItemModel.objects.filter(
        for_inventory=True,
        is_active=True,
    )


def calculate_expected_totals(item_model: ItemModel):
    """
    For a given ItemModel, calculate the expected inventory quantity and value
    based on RECEIVED ItemTransactionModel rows that are linked to a Bill.

    This mirrors the logic used when we recalc inventory_received & inventory_received_value.
    """

    agg = ItemTransactionModel.objects.filter(
        item_model=item_model,
        po_item_status=ItemTransactionModel.STATUS_RECEIVED,
        bill_model__isnull=False,
    ).aggregate(
        expected_qty=Coalesce(
            Sum('quantity'),
            0.0,
            output_field=DecimalField(max_digits=20, decimal_places=3),
        ),
        expected_value=Coalesce(
            Sum('total_amount'),
            0.0,
            output_field=DecimalField(max_digits=20, decimal_places=2),
        ),
    )

    expected_qty = agg['expected_qty'] or Decimal('0')
    expected_value = agg['expected_value'] or Decimal('0')

    return {
        'expected_qty': expected_qty,
        'expected_value': expected_value,
    }


def compare_item_totals(item_model: ItemModel):
    """
    Compare what is stored on the ItemModel (inventory_received, inventory_received_value)
    with what we calculate from ItemTransactionModel.

    Returns a dict describing:
    - if there is a mismatch
    - what the values are
    """

    # Stored values on the item
    stored_qty = item_model.inventory_received or Decimal('0')
    stored_value = item_model.inventory_received_value or Decimal('0')

    # Calculated values from transactions
    expected = calculate_expected_totals(item_model)
    expected_qty = expected['expected_qty']
    expected_value = expected['expected_value']

    # Simple comparison (you can add tolerances later if needed)
    qty_matches = (stored_qty == expected_qty)
    value_matches = (stored_value == expected_value)

    mismatch = not (qty_matches and value_matches)

    return {
        'item': item_model,
        'stored_qty': stored_qty,
        'stored_value': stored_value,
        'expected_qty': expected_qty,
        'expected_value': expected_value,
        'qty_matches': qty_matches,
        'value_matches': value_matches,
        'mismatch': mismatch,
    }
