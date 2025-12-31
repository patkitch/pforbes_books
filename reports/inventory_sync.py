from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Any, Optional

from django.db import transaction
from django.db.models import F
from django_ledger.models import EntityModel, ItemModel, ItemTransactionModel


# Helper: safe Decimal converter
def _to_decimal(val) -> Decimal:
    """
    Force anything (float, int, str, Decimal, None) into a Decimal.
    None -> Decimal('0')
    """
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
def _get_tx_qty(tx) -> Decimal:
    """
    Safely read the quantity received on this transaction row as Decimal.
    In your admin it's labeled 'Quantity:'.
    Django Ledger usually calls this field `quantity`.
    """
    return _to_decimal(getattr(tx, "quantity", 0))
def _get_tx_unit_cost(tx) -> Decimal:
    """
    Safely read the per-unit cost for this transaction row as Decimal.

    Different Django Ledger versions name this differently. We'll try a few:
    - 'cost_per_unit'   (what we *thought* it was)
    - 'unit_cost'
    - 'po_unit_cost'
    - 'po_unit_price'
    - 'cost' (last resort)

    Whatever we find first, we convert to Decimal.
    """
    for cand in [
        "cost_per_unit",
        "unit_cost",
        "po_unit_cost",
        "po_unit_price",
        "cost_per_item",
        "cost",
    ]:
        if hasattr(tx, cand):
            return _to_decimal(getattr(tx, cand))
    # if literally nothing matched, treat as zero cost
    return Decimal("0")



def rebuild_item_snapshots_for_entity(entity: EntityModel) -> Dict[str, Any]:
    """
    Rebuild ItemModel.inventory_received / inventory_received_value
    by looking at ItemTransactionModel for THIS entity.

    Returns a dict summary you can print/log.
    """

    # 1. get all item transactions for this entity where we actually received inventory
    # We consider "received" inventory only. You don't want ordered or in-transit.
    tx_qs = (
        ItemTransactionModel.objects.filter(
            item_model__entity_id=entity.uuid,
        )
        .filter(po_item_status__iexact="received")  # only things that actually landed
        .select_related("item_model")
        )


    rolled: Dict[str, Dict[str, Decimal]] = {}

    for tx in tx_qs:
        item_id = tx.item_model_id

        # quantity received on this line
        qty = _get_tx_qty(tx)  # Decimal
        unit_cost = _get_tx_unit_cost(tx)  # Decimal

        

        line_total_cost = (qty * unit_cost).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        if item_id not in rolled:
            rolled[item_id] = {
                "qty": Decimal("0"),
                "cost_total": Decimal("0"),
            }

        rolled[item_id]["qty"] += qty           # both are Decimal now
        rolled[item_id]["cost_total"] += line_total_cost

    # 2. write rolled totals back into each ItemModel.snapshot
    updated_items = 0
    zero_items = 0

    # We only touch items that belong to this entity.
    item_qs = ItemModel.objects.filter(entity_id=entity.uuid)

    with transaction.atomic():
        for item in item_qs:
            data = rolled.get(item.uuid)

            if not data:
                # nothing received ever (or nothing received left marked "received")
                # We'll leave item alone EXCEPT we keep it consistent:
                item.inventory_received = Decimal("0")
                item.inventory_received_value = Decimal("0")
                updated_items += 1
                zero_items += 1
                item.save(
                    update_fields=[
                        "inventory_received",
                        "inventory_received_value",
                        "updated",
                    ]
                )
                continue

            total_qty = data["qty"]
            total_cost_val = data["cost_total"]

            

            # Assign back into the snapshot that Django Ledger uses on ItemModel
            item.inventory_received = total_qty
            item.inventory_received_value = total_cost_val

            # NOTE: we are NOT touching accounting accounts (COGS, earnings, etc).
            # We are only rebuilding the snapshot totals that "available to sell" logic uses.

            item.save(
                update_fields=[
                    "inventory_received",
                    "inventory_received_value",
                    "updated",
                ]
            )
            updated_items += 1

    return {
        "entity": str(entity.slug),
        "items_considered": item_qs.count(),
        "items_updated": updated_items,
        "items_zeroed": zero_items,
        "rolled_count": len(rolled),
    }


def rebuild_all_entities() -> Dict[str, Dict[str, Any]]:
    """
    Run the rebuild for every entity that exists.
    Returns a dict keyed by entity slug with summary.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for entity in EntityModel.objects.all():
        out[str(entity.slug)] = rebuild_item_snapshots_for_entity(entity)
    return out
