"""
Sync service items (products/services) from Jobber to Forbes Lawn Accounting.

This command fetches all products and services from Jobber and creates/updates
ServiceItem records in the Forbes Lawn Accounting system.

Usage:
    python manage.py sync_jobber_items
    python manage.py sync_jobber_items --entity-slug forbes-lawn-spraying-llc-dev-d6qyx55c
"""

from django.core.management.base import BaseCommand
from django_ledger.models.entity import EntityModel
from forbes_lawn_accounting.services.service_item_sync import ServiceItemSyncService
import os


class Command(BaseCommand):
    help = 'Sync service items from Jobber API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug (defaults to FORBES_LAWN_ENTITY_SLUG env var)',
            default=os.getenv('FORBES_LAWN_ENTITY_SLUG'),
        )
        
        parser.add_argument(
            '--max-pages',
            type=int,
            default=100,
            help='Maximum number of pages to fetch (default: 100)',
        )
    
    def handle(self, *args, **options):
        entity_slug = options['entity_slug']
        max_pages = options['max_pages']
        
        if not entity_slug:
            self.stdout.write(self.style.ERROR(
                "Entity slug not provided. Set FORBES_LAWN_ENTITY_SLUG in .env "
                "or use --entity-slug flag."
            ))
            return
        
        # Get the entity
        try:
            entity = EntityModel.objects.get(slug=entity_slug)
            self.stdout.write(self.style.SUCCESS(f"✓ Found entity: {entity.name}"))
        except EntityModel.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Entity '{entity_slug}' not found"))
            return
        
        # Initialize sync service
        self.stdout.write("\n" + "="*60)
        self.stdout.write("SYNCING SERVICE ITEMS FROM JOBBER")
        self.stdout.write("="*60)
        
        try:
            syncer = ServiceItemSyncService(entity)
            
            self.stdout.write("\n📥 Fetching service items from Jobber...")
            
            # Sync all items
            stats = syncer.sync_all_items(max_pages=max_pages)
            
            # Display results
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("SYNC COMPLETE!"))
            self.stdout.write("="*60)
            
            self.stdout.write(f"\n📊 Results:")
            self.stdout.write(f"  Total Processed: {stats['total']}")
            self.stdout.write(self.style.SUCCESS(f"  Created: {stats['created']}"))
            self.stdout.write(self.style.SUCCESS(f"  Updated: {stats['updated']}"))
            
            if stats['errors'] > 0:
                self.stdout.write(self.style.ERROR(f"  Errors: {stats['errors']}"))
            else:
                self.stdout.write(f"  Errors: 0")
            
            if stats['total'] > 0:
                self.stdout.write(f"\n✅ Successfully synced {stats['total']} service items!")
                
                # Show breakdown by taxable status
                from forbes_lawn_accounting.models import ServiceItem
                taxable_count = ServiceItem.objects.filter(
                    entity=entity,
                    taxable=True
                ).count()
                nontaxable_count = ServiceItem.objects.filter(
                    entity=entity,
                    taxable=False
                ).count()
                
                self.stdout.write(f"\n📋 Breakdown:")
                self.stdout.write(f"  Taxable (→ 4024):     {taxable_count}")
                self.stdout.write(f"  Non-Taxable (→ 4025): {nontaxable_count}")
                
                self.stdout.write(f"\nView them at: /admin/forbes_lawn_accounting/serviceitem/")
            else:
                self.stdout.write(self.style.WARNING("\n⚠️ No service items found in Jobber"))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error during sync: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())
