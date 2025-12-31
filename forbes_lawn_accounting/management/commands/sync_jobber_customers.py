"""
Sync customers from Jobber to Forbes Lawn Accounting.

This command fetches all clients from Jobber and creates/updates
Customer records in the Forbes Lawn Accounting system.

Usage:
    python manage.py sync_jobber_customers
    python manage.py sync_jobber_customers --entity-slug forbes-lawn-spraying-llc-dev-d6qyx55c
"""

from django.core.management.base import BaseCommand
from django_ledger.models.entity import EntityModel
from forbes_lawn_accounting.services.customer_sync import CustomerSyncService
import os


class Command(BaseCommand):
    help = 'Sync customers from Jobber API'
    
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
        self.stdout.write("SYNCING CUSTOMERS FROM JOBBER")
        self.stdout.write("="*60)
        
        try:
            syncer = CustomerSyncService(entity)
            
            self.stdout.write("\n📥 Fetching customers from Jobber...")
            
            # Sync all customers
            stats = syncer.sync_all_customers(max_pages=max_pages)
            
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
                self.stdout.write(f"\n✅ Successfully synced {stats['total']} customers!")
                self.stdout.write(f"\nView them at: /admin/forbes_lawn_accounting/customer/")
            else:
                self.stdout.write(self.style.WARNING("\n⚠️ No customers found in Jobber"))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error during sync: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())
