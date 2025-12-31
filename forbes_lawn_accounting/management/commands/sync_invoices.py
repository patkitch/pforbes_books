from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService


class Command(BaseCommand):
    help = 'Sync invoices from Jobber to LedgerLink'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for invoice sync (YYYY-MM-DD format)',
            default=None
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Fetch invoices but do not post to ledger'
        )

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        ledgerlink_api_key = os.environ.get("LEDGERLINK_API_KEY")
        entity_slug = "forbes-lawn-spraying-llc-dev-d6qyx55c"
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY environment variable not set")
        
        if not ledgerlink_api_key:
            raise CommandError("LEDGERLINK_API_KEY environment variable not set")
        
        start_date = options.get('start_date')
        dry_run = options.get('dry_run', False)
        
        self.stdout.write("Starting invoice sync...")
        if start_date:
            self.stdout.write(f"Start Date: {start_date}")
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug=entity_slug
        )
        
        try:
            stats = service.sync_invoices(
                start_date=start_date,
                dry_run=dry_run
            )
            
            self.stdout.write("\n" + "="*60)
            self.stdout.write("SYNC COMPLETE")
            self.stdout.write("="*60)
            self.stdout.write(f"Total invoices: {stats['total']}")
            self.stdout.write(f"Posted: {stats['posted']}")
            self.stdout.write(f"Skipped: {stats['skipped']}")
            self.stdout.write(f"Errors: {stats['errors']}")
            
            if stats['errors'] > 0:
                self.stdout.write(self.style.WARNING(
                    f"\nWarning: {stats['errors']} invoices had errors"
                ))
            else:
                self.stdout.write(self.style.SUCCESS("\nInvoice sync completed successfully!"))
                
        except Exception as e:
            raise CommandError(f"Invoice sync failed: {e}")
