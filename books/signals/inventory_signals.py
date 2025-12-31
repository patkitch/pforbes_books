from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce

from django_ledger.models import ItemTransactionModel, ItemModel


def _recalc_item_totals(item_model: ItemModel):
    """
    Recalculate the totals for a single ItemModel based on all RECEIVED ItemTransactionModel rows
    that are linked to a Bill.
    """
    agg = ItemTransactionModel.objects.filter(
        item_model=item_model,
        po_item_status=ItemTransactionModel.STATUS_RECEIVED,
        bill_model__isnull=False,
    ).aggregate(
        total_qty=Coalesce(
            Sum('quantity'),
            0.0,
            output_field=DecimalField(max_digits=20, decimal_places=3),
        ),
        total_cost=Coalesce(
            Sum('total_amount'),
            0.0,
            output_field=DecimalField(max_digits=20, decimal_places=2),
        ),
    )

    item_model.inventory_received = agg['total_qty'] or Decimal('0')
    item_model.inventory_received_value = agg['total_cost'] or Decimal('0')

    item_model.save(update_fields=['inventory_received', 'inventory_received_value'])
@receiver(post_save, sender=ItemTransactionModel)
def sync_item_totals_on_save(sender, instance: ItemTransactionModel, **kwargs):
    """
    Whenever an ItemTransactionModel is saved, if it's RECEIVED and tied to a Bill, recalc that item's totals.
    """
    if (
        instance.po_item_status == ItemTransactionModel.STATUS_RECEIVED
        and instance.bill_model_id is not None
        and instance.item_model_id is not None
    ):
        _recalc_item_totals(instance.item_model)