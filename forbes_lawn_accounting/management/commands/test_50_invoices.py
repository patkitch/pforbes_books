"""
Test fetching 50 invoices (the default limit)
"""

from django.core.management.base import BaseCommand, CommandError
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService


class Command(BaseCommand):
    help = 'Test fetching 50 invoices'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        ledgerlink_api_key = os.environ.get("LEDGERLINK_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        if not ledgerlink_api_key:
            raise CommandError("LEDGERLINK_API_KEY not set")
        
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug="forbes-lawn-spraying-llc-dev-d6qyx55c"
        )
        
        self.stdout.write("Fetching 50 invoices at once...")
        
        try:
            result = service.fetch_jobber_invoices(
                limit=50,  # Default limit
                start_date="2025-01-01"
            )
            
            if "errors" in result:
                self.stdout.write(self.style.ERROR(f"ERROR: {result['errors']}"))
            else:
                self.stdout.write(self.style.SUCCESS("✓ Fetch successful!"))
                invoices = result['data']['invoices']['nodes']
                self.stdout.write(f"Found {len(invoices)} invoices")
                
                # Show rate limit
                extensions = result.get('extensions', {})
                cost = extensions.get('cost', {})
                throttle = cost.get('throttleStatus', {})
                available = throttle.get('currentlyAvailable', 'unknown')
                requested = cost.get('requestedQueryCost', 'unknown')
                actual = cost.get('actualQueryCost', 'unknown')
                
                self.stdout.write(f"\nRequested cost: {requested} points")
                self.stdout.write(f"Actual cost: {actual} points")
                self.stdout.write(f"Remaining: {available}/10000")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception: {e}"))
            import traceback
            traceback.print_exc()
