"""
Django Management Command: sync_service_items
Syncs service items/products from Jobber
"""

from django.core.management.base import BaseCommand, CommandError
from forbes_lawn_accounting.services.service_items_sync_service import ServiceItemsSyncService
import os


class Command(BaseCommand):
    help = 'Sync service items/products from Jobber'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-file',
            type=str,
            help='Output JSON file path',
            default='service_items.json'
        )

    def handle(self, *args, **options):
        # Get API key from environment
        jobber_key = os.environ.get('JOBBER_API_KEY')
        
        if not jobber_key:
            raise CommandError('JOBBER_API_KEY environment variable not set')
        
        output_file = options['output_file']
        
        self.stdout.write(self.style.SUCCESS('Starting service items sync...'))
        self.stdout.write('')
        
        try:
            service = ServiceItemsSyncService(jobber_api_key=jobber_key)
            
            stats = service.sync_service_items(output_file=output_file)
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ Service items sync completed!'))
            self.stdout.write(f'Total: {stats["total_fetched"]}')
            self.stdout.write(f'Saved to: {output_file}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            raise CommandError(f'Service items sync failed: {str(e)}')