# stockops/services.py
from decimal import Decimal
from django_ledger.models.items import ItemTransactionModel

def get_txn_on_hand(entity_model, item_model) -> Decimal:
    """
    Returns on-hand strictly from ItemTransactionModel roll-up (ignores ItemModel snapshot).
    Uses django_ledger's inventory_count aggregation.
    """
    qs = ItemTransactionModel.objects.inventory_count(entity_model=entity_model)

    # Try DB-side filter first (qs may be a ValuesQueryset of dicts)
    try:
        row = qs.filter(item_model_id=item_model.uuid).values("quantity_onhand").first()
        if row:
            return row.get("quantity_onhand") or Decimal("0")
    except Exception:
        # Fallback: iterate results (dicts)
        for r in qs:
            if r.get("item_model_id") == item_model.uuid:
                return r.get("quantity_onhand") or Decimal("0")

    return Decimal("0")
