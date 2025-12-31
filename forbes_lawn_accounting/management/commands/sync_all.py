"""
Django Management Command: sync_all
Syncs all data from Jobber to LedgerLink (service items, invoices, payments)
"""

from django.core.management.base import BaseCommand, CommandError
from forbes_lawn_accounting.services.service_items_sync_service import ServiceItemsSyncService
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService
from forbes_lawn_accounting.services.payment_sync_service import PaymentSyncService
import os
from datetime import datetime


class Command(BaseCommand):
    help = 'Sync all data from Jobber to LedgerLink (service items, invoices, payments)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for invoice/payment sync (YYYY-MM-DD)',
            default='2024-01-01'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Fetch data but do not post to ledger (test mode)',
        )
        parser.add_argument(
            '--skip-service-items',
            action='store_true',
            help='Skip service items sync (if already completed)',
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
        skip_service_items = options['skip_service_items']
        entity_slug = options['entity_slug']
        
        # Print header
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('FORBES LAWN ACCOUNTING - COMPLETE SYNC'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Entity: {entity_slug}')
        self.stdout.write(f'Start Date: {start_date}')
        self.stdout.write(f'Mode: {"DRY RUN" if dry_run else "LIVE"}')
        self.stdout.write('=' * 70)
        self.stdout.write('')
        
        results = {
            'started_at': datetime.now().isoformat(),
            'entity_slug': entity_slug,
            'start_date': start_date,
            'dry_run': dry_run
        }
        
        try:
            # Step 1: Service Items
            if not skip_service_items:
                self.stdout.write('')
                self.stdout.write('=' * 70)
                self.stdout.write(self.style.WARNING('STEP 1: SYNCING SERVICE ITEMS'))
                self.stdout.write('=' * 70)
                
                service_items_service = ServiceItemsSyncService(jobber_key)
                service_items_stats = service_items_service.sync_service_items()
                results['service_items'] = service_items_stats
            else:
                self.stdout.write('')
                self.stdout.write(self.style.WARNING('⊘ Skipping service items sync'))
                results['service_items'] = {'skipped': True}
            
            # Step 2: Invoices
            self.stdout.write('')
            self.stdout.write('=' * 70)
            self.stdout.write(self.style.WARNING('STEP 2: SYNCING INVOICES'))
            self.stdout.write('=' * 70)
            
            invoice_service = InvoiceSyncService(
                jobber_api_key=jobber_key,
                ledgerlink_api_key=ledgerlink_key,
                entity_slug=entity_slug
            )
            invoice_stats = invoice_service.sync_invoices(
                start_date=start_date,
                dry_run=dry_run
            )
            results['invoices'] = invoice_stats
            
            # Step 3: Payments
            self.stdout.write('')
            self.stdout.write('=' * 70)
            self.stdout.write(self.style.WARNING('STEP 3: SYNCING PAYMENTS'))
            self.stdout.write('=' * 70)
            
            payment_service = PaymentSyncService(
                jobber_api_key=jobber_key,
                ledgerlink_api_key=ledgerlink_key,
                entity_slug=entity_slug
            )
            payment_stats = payment_service.sync_payments(
                start_date=start_date,
                dry_run=dry_run
            )
            results['payments'] = payment_stats
            
            # Final summary
            results['completed_at'] = datetime.now().isoformat()
            self._print_final_summary(results)
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ Sync completed successfully!'))
            
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'✗ Error during sync: {str(e)}'))
            raise CommandError(f'Sync failed: {str(e)}')
    
    def _print_final_summary(self, results):
        """Print comprehensive summary"""
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('COMPLETE SYNC SUMMARY'))
        self.stdout.write('=' * 70)
        
        # Service Items
        if 'service_items' in results and not results['service_items'].get('skipped'):
            si = results['service_items']
            if 'error' not in si:
                self.stdout.write('')
                self.stdout.write('📦 Service Items:')
                self.stdout.write(f'   Total: {si.get("total_fetched", 0)}')
                self.stdout.write(f'   Taxable: {si.get("taxable", 0)}')
                self.stdout.write(f'   Non-Taxable: {si.get("non_taxable", 0)}')
        
        # Invoices
        if 'invoices' in results:
            inv = results['invoices']
            if 'error' not in inv:
                self.stdout.write('')
                self.stdout.write('📄 Invoices:')
                self.stdout.write(f'   Fetched: {inv.get("total_fetched", 0)}')
                self.stdout.write(f'   Posted: {inv.get("posted", 0)}')
                self.stdout.write(f'   Skipped: {inv.get("skipped", 0)}')
                self.stdout.write(f'   Errors: {len(inv.get("errors", []))}')
                
                if inv.get('invoices'):
                    total_revenue = sum(float(i['amount']) for i in inv['invoices'])
                    self.stdout.write(f'   Total Revenue Posted: ${total_revenue:,.2f}')
        
        # Payments
        if 'payments' in results:
            pmt = results['payments']
            if 'error' not in pmt:
                self.stdout.write('')
                self.stdout.write('💰 Payments:')
                self.stdout.write(f'   Fetched: {pmt.get("total_fetched", 0)}')
                self.stdout.write(f'   Posted: {pmt.get("posted", 0)}')
                self.stdout.write(f'   Skipped: {pmt.get("skipped", 0)}')
                self.stdout.write(f'   Errors: {len(pmt.get("errors", []))}')
                
                if pmt.get('payments'):
                    total_payments = sum(float(p['amount']) for p in pmt['payments'])
                    self.stdout.write(f'   Total Payments Posted: ${total_payments:,.2f}')
        
        self.stdout.write('')
        self.stdout.write('=' * 70)