from django.core.management.base import BaseCommand, CommandError
from django_ledger.models import EntityModel

from reports.inventory_sync import (
    rebuild_item_snapshots_for_entity,
    rebuild_all_entities,
)


class Command(BaseCommand):
    help = (
        "Rebuild ItemModel.inventory_received and inventory_received_value "
        "from ItemTransactionModel for one entity or all entities."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity",
            type=str,
            help="Entity slug to rebuild. If omitted, rebuilds ALL entities.",
        )

    def handle(self, *args, **options):
        entity_slug = options.get("entity")

        if entity_slug:
            try:
                entity = EntityModel.objects.get(slug__exact=entity_slug)
            except EntityModel.DoesNotExist:
                raise CommandError(f"Entity {entity_slug} not found.")

            result = rebuild_item_snapshots_for_entity(entity)
            self.stdout.write(self.style.SUCCESS(f"[OK] Rebuilt {entity_slug}: {result}"))
        else:
            result = rebuild_all_entities()
            self.stdout.write(self.style.SUCCESS("[OK] Rebuilt ALL entities"))
            for slug, summary in result.items():
                self.stdout.write(f" - {slug}: {summary}")
