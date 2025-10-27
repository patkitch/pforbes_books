from django.core.management.base import BaseCommand
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django_ledger.models import ItemTransactionModel


class Command(BaseCommand):
    help = "Rebuild each Item's total_inventory_received and total_value_received from RECEIVED PO lines."

    def handle(self, *args, **options):
        # We only care about PO lines that are marked RECEIVED.
        received_lines = ItemTransactionModel.objects.filter(
            po_item_status=ItemTransactionModel.STATUS_RECEIVED,
            item_model__isnull=False,
            po_quantity__gt=0,
            po_unit_cost__gt=0
        )

        # We'll summarize by item_model.
        # total_qty = sum(po_quantity)
        # total_value = sum(po_quantity * po_unit_cost)
        lines_by_item = (
            received_lines
            .values('item_model')  # group by the FK to Item
            .annotate(
                total_qty=Sum('po_quantity'),
                total_value=Sum(
                    ExpressionWrapper(
                        F('po_quantity') * F('po_unit_cost'),
                        output_field=DecimalField(max_digits=20, decimal_places=2)
                    )
                )
            )
        )

        updated_items = 0

        # For each item, write the totals directly onto the Item model.
        for row in lines_by_item:
            item = received_lines.first().item_model.__class__.objects.get(pk=row['item_model'])
            item.total_inventory_received = row['total_qty'] or 0
            item.total_value_received = row['total_value'] or 0
            item.save(update_fields=['total_inventory_received', 'total_value_received'])
            updated_items += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated_items} items with rebuilt totals."
            )
        )
