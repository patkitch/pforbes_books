# books/signals/inventory_signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_ledger.models import ItemTransactionModel


@receiver(post_save, sender=ItemTransactionModel)
def update_item_inventory_on_receipt(sender, instance, **kwargs):
    """
    Updates ItemModel inventory totals when a PO line is marked RECEIVED.
    """

    po_status = getattr(instance, "po_item_status", None)
    item_obj = getattr(instance, "item_model", None)
    qty = getattr(instance, "po_quantity", None)
    unit_cost = getattr(instance, "po_unit_cost", None)

    # Only proceed for valid received items
    if not item_obj or po_status != ItemTransactionModel.STATUS_RECEIVED:
        return
    if not qty or not unit_cost:
        return

    # Update item totals
    item_obj.total_inventory_received = (item_obj.total_inventory_received or 0) + qty
    item_obj.total_value_received = (item_obj.total_value_received or 0) + (qty * unit_cost)
    item_obj.save(update_fields=["total_inventory_received", "total_value_received"])
