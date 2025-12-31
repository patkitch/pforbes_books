from django_ledger.models import ItemTransactionModel

qs = ItemTransactionModel.objects.filter(
    po_item_status=ItemTransactionModel.STATUS_RECEIVED
)

count = 0

for line in qs:
    item_obj = getattr(line, "item_model", None)
    qty = getattr(line, "po_quantity", None)
    unit_cost = getattr(line, "po_unit_cost", None)

    # skip incomplete/invalid rows
    if not item_obj or not qty or not unit_cost or qty <= 0:
        continue

    # saving the line will fire your post_save signal,
    # which updates total_inventory_received / total_value_received
    line.save()
    count += 1

print(f"Resaved {count} received PO lines.")
