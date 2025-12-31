"""
Test the full sync_invoices method
"""

from django.core.management.base import BaseCommand, CommandError
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService


class Command(BaseCommand):
    help = 'Test full sync_invoices method'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        ledgerlink_api_key = os.environ.get("LEDGERLINK_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        if not ledgerlink_api_key:
            raise CommandError("LEDGERLINK_API_KEY not set")
        
        self.stdout.write("Creating service...")
        
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug="forbes-lawn-spraying-llc-dev-d6qyx55c"
        )
        
        self.stdout.write("✓ Service created")
        self.stdout.write("Calling sync_invoices (dry-run)...")
        
        try:
            stats = service.sync_invoices(
                start_date="2025-01-01",
                dry_run=True
            )
            
            self.stdout.write(self.style.SUCCESS("✓ Sync completed!"))
            self.stdout.write(f"Total: {stats['total']}")
            self.stdout.write(f"Posted: {stats['posted']}")
            self.stdout.write(f"Skipped: {stats['skipped']}")
            self.stdout.write(f"Errors: {stats['errors']}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception: {e}"))
            import traceback
            traceback.print_exc()
