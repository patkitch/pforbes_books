from django.core.management.base import BaseCommand
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce

from django_ledger.models import ItemModel, ItemTransactionModel


class Command(BaseCommand):
    help = "Rebuild inventory_received and inventory_received_value on ItemModel from received PO/Bill lines."

    def handle(self, *args, **options):
        # We'll aggregate per ItemModel using only RECEIVED inventory from Bills/POs.
        # Logic:
        #  - Only look at ItemTransactionModel rows that:
        #       * have po_item_status == 'received'
        #       * and are linked to a Bill (bill_model_id is not null),
        #    because those represent inventory you actually took possession of and paid for.
        #
        #  - Sum quantity and total_amount per item_model.

        received_qs = ItemTransactionModel.objects.filter(
            po_item_status=ItemTransactionModel.STATUS_RECEIVED,
            bill_model__isnull=False,
        ).values(
            'item_model_id'
        ).annotate(
            total_qty=Coalesce(
                Sum('quantity'),
                0.0,
                output_field=DecimalField(max_digits=20, decimal_places=3)
            ),
            total_cost=Coalesce(
                Sum('total_amount'),
                0.0,
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
        )

        # Turn that into a dict keyed by item_model_id
        totals_by_item = {
            row['item_model_id']: {
                'qty': row['total_qty'],
                'cost': row['total_cost'],
            }
            for row in received_qs
        }

        updated = 0

        # Loop through all items that are inventory or products (anything that can be stocked)
        for item in ItemModel.objects.all():
            data = totals_by_item.get(item.uuid)

            if data:
                item.inventory_received = data['qty']
                item.inventory_received_value = data['cost']
            else:
                # If nothing received for this item, set zero instead of leaving None.
                item.inventory_received = 0
                item.inventory_received_value = 0

            # Save to the correct field names on your model
            item.save(update_fields=['inventory_received', 'inventory_received_value'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f'Updated {updated} items with rebuilt totals.'))

