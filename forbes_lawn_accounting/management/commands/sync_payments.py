"""
Django Management Command: sync_payments
Syncs payments from Jobber to LedgerLink
"""

from django.core.management.base import BaseCommand, CommandError
from forbes_lawn_accounting.services.payment_sync_service import PaymentSyncService
import os


class Command(BaseCommand):
    help = 'Sync payments from Jobber to LedgerLink'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for sync (YYYY-MM-DD)',
            default='2024-01-01'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Fetch data but do not post to ledger (test mode)',
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='LedgerLink entity slug',
            default='forbes-lawn-spraying-llc-dev-d6qyx55c'
        )

    def handle(self, *args, **options):
        # Get API keys from environment
        jobber_key = os.environ.get('JOBBER_API_KEY')
        ledgerlink_key = os.environ.get('LEDGERLINK_API_KEY')
        
        if not jobber_key:
            raise CommandError('JOBBER_API_KEY environment variable not set')
        
        if not ledgerlink_key:
            raise CommandError('LEDGERLINK_API_KEY environment variable not set')
        
        # Parse options
        start_date = options['start_date']
        dry_run = options['dry_run']
        entity_slug = options['entity_slug']
        
        self.stdout.write(self.style.SUCCESS('Starting payment sync...'))
        self.stdout.write(f'Start Date: {start_date}')
        self.stdout.write(f'Mode: {"DRY RUN" if dry_run else "LIVE"}')
        self.stdout.write('')
        
        try:
            service = PaymentSyncService(
                jobber_api_key=jobber_key,
                ledgerlink_api_key=ledgerlink_key,
                entity_slug=entity_slug
            )
            
            stats = service.sync_payments(
                start_date=start_date,
                dry_run=dry_run
            )
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ Payment sync completed!'))
            self.stdout.write(f'Posted: {stats["posted"]}')
            self.stdout.write(f'Errors: {len(stats["errors"])}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            raise CommandError(f'Payment sync failed: {str(e)}')