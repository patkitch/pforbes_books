from django.core.management.base import BaseCommand, CommandError
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService


class Command(BaseCommand):
    help = 'Test syncing just 1 invoice to LedgerLink'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        ledgerlink_api_key = os.environ.get("LEDGERLINK_API_KEY")
        entity_slug = "forbes-lawn-spraying-llc-dev-d6qyx55c"
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        if not ledgerlink_api_key:
            raise CommandError("LEDGERLINK_API_KEY not set")
        
        self.stdout.write("Fetching 1 invoice from Jobber...")
        
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug=entity_slug
        )
        
        # Fetch just 1 invoice
        result = service.fetch_jobber_invoices(
            limit=1,
            start_date="2025-01-01"
        )
        
        if "errors" in result:
            raise CommandError(f"Failed to fetch: {result['errors']}")
        
        invoice = result['data']['invoices']['nodes'][0]
        self.stdout.write(f"Fetched Invoice #{invoice['invoiceNumber']}: ")
        self.stdout.write(f"Status: {invoice['invoiceStatus']}")
        
        # Post to LedgerLink
        self.stdout.write("\nPosting to LedgerLink...")
        
        try:
            ledger_result = service.create_ledger_entry_for_invoice(invoice)
            
            if "errors" in ledger_result and ledger_result["errors"]:
                self.stdout.write(self.style.ERROR(f"LedgerLink error: {ledger_result['errors']}"))
            else:
                ledger_entry = ledger_result["data"]["createLedgerEntry"]["ledgerEntry"]
                self.stdout.write(self.style.SUCCESS(
                    f"Success! Posted as entry #{ledger_entry['entryNumber']}"
                ))
                self.stdout.write(f"Entry ID: {ledger_entry['id']}")
                self.stdout.write(f"Total Debit: ")
                self.stdout.write(f"Total Credit: ")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception: {e}"))
            import traceback
            traceback.print_exc()
