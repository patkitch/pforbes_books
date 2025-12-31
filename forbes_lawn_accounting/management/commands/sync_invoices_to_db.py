"""
Simple Invoice Sync - Save to Django Database
"""
from django.core.management.base import BaseCommand, CommandError
import os
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService
from forbes_lawn_accounting.models import Invoice, InvoiceLine, Customer
from decimal import Decimal
from django.utils.dateparse import parse_datetime


class Command(BaseCommand):
    help = 'Sync invoices from Jobber and save to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD)',
            default=None
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of invoices to sync',
            default=None
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug for invoices',
            default='forbes-lawn-spraying-llc-dev-d6qyx55c'
        )

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        start_date = options.get('start_date')
        limit = options.get('limit')
        entity_slug = options.get('entity_slug')
        
        self.stdout.write(f"Syncing invoices to database...")
        if start_date:
            self.stdout.write(f"Start date: {start_date}")
        if limit:
            self.stdout.write(f"Limit: {limit}")
        self.stdout.write(f"Entity: {entity_slug}")
        
        # Fetch invoices
        service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key="not-needed",
            entity_slug="not-needed"
        )
        
        if limit:
            # Fetch specific number
            result = service.fetch_jobber_invoices(limit=limit, start_date=start_date)
            invoices = result['data']['invoices']['nodes']
        else:
            # Fetch all
            invoices = service.fetch_all_jobber_invoices(start_date=start_date)
        
        self.stdout.write(f"\nProcessing {len(invoices)} invoices...")
        
        created = 0
        updated = 0
        errors = 0
        
        for inv_data in invoices:
            try:
                # Get or create customer
                client_data = inv_data['client']
                
                # Build customer name from available fields
                if 'name' in client_data:
                    customer_name = client_data['name']
                elif 'companyName' in client_data and client_data['companyName']:
                    customer_name = client_data['companyName']
                else:
                    # Combine firstName and lastName
                    first = client_data.get('firstName', '')
                    last = client_data.get('lastName', '')
                    customer_name = f"{first} {last}".strip()
                
                customer, _ = Customer.objects.get_or_create(
                    jobber_client_id=client_data['id'],
                    defaults={'name': customer_name}
                )
                
                from django.utils import timezone
                from django_ledger.models import EntityModel
                
                # Get entity by slug
                entity = EntityModel.objects.get(slug=entity_slug)
                
                invoice, is_new = Invoice.objects.update_or_create(
                    jobber_invoice_id=inv_data['id'],
                    defaults={
                        'entity': entity,
                        'customer': customer,
                        'invoice_number': inv_data['invoiceNumber'],
                        'internal_notes': inv_data.get('subject', ''),
                        'note_to_customer': inv_data.get('message') or '',
                        'invoice_date': parse_datetime(inv_data['issuedDate']) if inv_data.get('issuedDate') else None,
                        'due_date': parse_datetime(inv_data['dueDate']) if inv_data.get('dueDate') else None,
                        'status': inv_data['invoiceStatus'],
                        'total': Decimal(str(inv_data['amounts']['total'])),
                        'subtotal': Decimal(str(inv_data['amounts']['subtotal'])),
                        'tax_amount': Decimal(str(inv_data['amounts']['taxAmount'])),
                        'balance_due': Decimal(str(inv_data['amounts']['invoiceBalance'])),
                        'amount_paid': Decimal(str(inv_data['amounts']['paymentsTotal'])),
                        'synced_at': timezone.now(),
                    }
                )
                
                if is_new:
                    created += 1
                    self.stdout.write(f"✓ Created invoice #{inv_data['invoiceNumber']}")
                else:
                    updated += 1
                    self.stdout.write(f"✓ Updated invoice #{inv_data['invoiceNumber']}")
                
                # Create line items
                for idx, line_data in enumerate(inv_data['lineItems']['nodes'], start=1):
                    InvoiceLine.objects.create(
                        invoice=invoice,
                        line_number=idx,
                        description=line_data['name'],
                        quantity=Decimal(str(line_data['quantity'])),
                        rate=Decimal(str(line_data['unitPrice'])),
                        amount=Decimal(str(line_data['totalPrice']))
                    )
                    
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(
                    f"✗ Error with invoice #{inv_data.get('invoiceNumber', '?')}: {e}"
                ))
                # Print full traceback for debugging
                import traceback
                traceback.print_exc()
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write("SYNC COMPLETE")
        self.stdout.write("="*60)
        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Updated: {updated}")
        self.stdout.write(f"Errors: {errors}")
        self.stdout.write(f"Total: {created + updated}")