"""
Test calling the actual InvoiceSyncService
"""

from django.core.management.base import BaseCommand, CommandError
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService


class Command(BaseCommand):
    help = 'Test calling InvoiceSyncService directly'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        ledgerlink_api_key = os.environ.get("LEDGERLINK_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        if not ledgerlink_api_key:
            raise CommandError("LEDGERLINK_API_KEY not set")
        
        self.stdout.write("Creating InvoiceSyncService...")
        
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug="forbes-lawn-spraying-llc-dev-d6qyx55c"
        )
        
        self.stdout.write("✓ Service created")
        self.stdout.write("Calling fetch_jobber_invoices with limit=2...")
        
        try:
            result = service.fetch_jobber_invoices(
                limit=2,
                start_date="2025-01-01"
            )
            
            if "errors" in result:
                self.stdout.write(self.style.ERROR(f"ERROR: {result['errors']}"))
            else:
                self.stdout.write(self.style.SUCCESS("✓ Fetch successful!"))
                invoices = result['data']['invoices']['nodes']
                self.stdout.write(f"Found {len(invoices)} invoices")
                
                # Show rate limit from response
                extensions = result.get('extensions', {})
                cost = extensions.get('cost', {})
                throttle = cost.get('throttleStatus', {})
                available = throttle.get('currentlyAvailable', 'unknown')
                actual_cost = cost.get('actualQueryCost', 'unknown')
                
                self.stdout.write(f"Query cost: {actual_cost} points")
                self.stdout.write(f"Remaining: {available}/10000")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception: {e}"))
