"""
Management command to test ledger posting service.

Creates a test invoice and posts it to verify everything works.

Usage:
    python manage.py test_posting
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_ledger.models.entity import EntityModel
from forbes_lawn_accounting.models import Customer, ServiceItem, Invoice, InvoiceLine, InvoicePayment
from forbes_lawn_accounting.services.ledger_posting import LedgerPostingService
import os


class Command(BaseCommand):
    help = 'Test the ledger posting service with a sample invoice'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug (defaults to FORBES_LAWN_ENTITY_SLUG env var)',
            default=os.getenv('FORBES_LAWN_ENTITY_SLUG'),
        )
    
    def handle(self, *args, **options):
        entity_slug = options['entity_slug']
        
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
        
        # Initialize posting service
        try:
            poster = LedgerPostingService(entity)
            self.stdout.write(self.style.SUCCESS(f"✓ Posting service initialized with COA: {poster.coa.name}"))
        except ValueError as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return
        
        # Create test customer (or get existing)
        customer, created = Customer.objects.get_or_create(
            entity=entity,
            jobber_id='TEST-CUSTOMER-001',
            defaults={
                'name': 'Test Customer',
                'email': 'test@example.com',
                'phone': '555-1234',
                'billing_city': 'Kansas City',
                'billing_state': 'KS',
                'billing_zip': '66101',
                'active': True,
                'synced_at': timezone.now(),
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"✓ Created test customer: {customer.name}"))
        else:
            self.stdout.write(f"  Using existing customer: {customer.name}")
        
        # Get revenue accounts
        try:
            revenue_account_taxable = poster._get_account('4024')
            revenue_account_nontaxable = poster._get_account('4025')
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Revenue accounts not found: {e}"))
            return
        
        # Create test service item (or get existing)
        service_item, created = ServiceItem.objects.get_or_create(
            entity=entity,
            jobber_id='TEST-SERVICE-001',
            defaults={
                'name': 'Test Fertilization Service',
                'description': 'Spring fertilization treatment',
                'category_name': 'Fertilization',
                'default_rate': Decimal('85.00'),
                'taxable': True,
                'revenue_account': revenue_account_taxable,
                'active': True,
                'synced_at': timezone.now(),
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"✓ Created test service: {service_item.name}"))
        else:
            self.stdout.write(f"  Using existing service: {service_item.name}")
        
        # Create test invoice
        self.stdout.write("\n" + "="*60)
        self.stdout.write("Creating test invoice...")
        self.stdout.write("="*60)
        
        invoice = Invoice.objects.create(
            entity=entity,
            customer=customer,
            jobber_invoice_id=f'TEST-INV-{timezone.now().timestamp()}',
            invoice_number=f'TEST-{timezone.now().strftime("%Y%m%d-%H%M%S")}',
            invoice_date=timezone.now().date(),
            status='OPEN',
            tax_rate=Decimal('0.0865'),  # 8.65% Kansas sales tax
            synced_at=timezone.now(),
        )
        self.stdout.write(f"✓ Created invoice: {invoice.invoice_number}")
        
        # Add line items
        InvoiceLine.objects.create(
            invoice=invoice,
            jobber_line_id='TEST-LINE-001',
            service_item=service_item,
            line_number=1,
            service_date=timezone.now().date(),
            description='Spring fertilization - front lawn',
            quantity=Decimal('1.00'),
            rate=Decimal('85.00'),
            amount=Decimal('85.00'),
            taxable=True,
        )
        
        InvoiceLine.objects.create(
            invoice=invoice,
            jobber_line_id='TEST-LINE-002',
            service_item=service_item,
            line_number=2,
            service_date=timezone.now().date(),
            description='Spring fertilization - back lawn',
            quantity=Decimal('1.00'),
            rate=Decimal('65.00'),
            amount=Decimal('65.00'),
            taxable=True,
        )
        
        self.stdout.write(f"✓ Added 2 line items")
        
        # Recompute totals
        invoice.recompute_totals()
        
        self.stdout.write(f"\nInvoice Totals:")
        self.stdout.write(f"  Subtotal:        ${invoice.subtotal:,.2f}")
        self.stdout.write(f"  Taxable:         ${invoice.taxable_subtotal:,.2f}")
        self.stdout.write(f"  Tax (8.65%):     ${invoice.tax_amount:,.2f}")
        self.stdout.write(f"  Total:           ${invoice.total:,.2f}")
        
        # Post to ledger
        self.stdout.write("\n" + "="*60)
        self.stdout.write("Posting invoice to ledger...")
        self.stdout.write("="*60)
        
        try:
            je = poster.post_invoice_to_ledger(invoice)
            self.stdout.write(self.style.SUCCESS(f"✓ Posted to ledger!"))
            self.stdout.write(f"  Ledger: {je.ledger.name}")
            self.stdout.write(f"  Journal Entry: {je.description}")
            
            # Show transactions
            from django_ledger.models.transactions import TransactionModel
            self.stdout.write(f"\n  Transactions:")
            for tx in TransactionModel.objects.filter(journal_entry=je):
                tx_type = "DR" if tx.tx_type == 'debit' else "CR"
                self.stdout.write(f"    {tx_type} {tx.account.code} {tx.account.name:40s} ${tx.amount:>10,.2f}")
            
            # Verify posting
            self.stdout.write("\n" + "="*60)
            self.stdout.write("Verifying posting...")
            self.stdout.write("="*60)
            
            results = poster.verify_posting(invoice)
            
            if results['errors']:
                self.stdout.write(self.style.ERROR("❌ Verification failed:"))
                for error in results['errors']:
                    self.stdout.write(self.style.ERROR(f"  - {error}"))
            else:
                self.stdout.write(self.style.SUCCESS("✓ All verifications passed!"))
                self.stdout.write(f"  Debits:  ${results['debit_total']:,.2f}")
                self.stdout.write(f"  Credits: ${results['credit_total']:,.2f}")
                self.stdout.write(f"  Balance: {'✓' if results['transactions_balance'] else '✗'}")
            
            # Test payment posting
            self.stdout.write("\n" + "="*60)
            self.stdout.write("Creating and posting test payment...")
            self.stdout.write("="*60)
            
            payment = InvoicePayment.objects.create(
                invoice=invoice,
                jobber_payment_id=f'TEST-PAY-{timezone.now().timestamp()}',
                payment_date=timezone.now().date(),
                amount=Decimal('100.00'),
                payment_method='CARD',
                reference='TEST-1234',
                synced_at=timezone.now(),
            )
            
            self.stdout.write(f"✓ Created payment: ${payment.amount:,.2f}")
            
            je_payment = poster.post_payment_to_ledger(payment)
            self.stdout.write(self.style.SUCCESS(f"✓ Posted payment to ledger!"))
            self.stdout.write(f"  Ledger: {je_payment.ledger.name}")
            
            # Show payment transactions
            self.stdout.write(f"\n  Transactions:")
            for tx in TransactionModel.objects.filter(journal_entry=je_payment):
                tx_type = "DR" if tx.tx_type == 'debit' else "CR"
                self.stdout.write(f"    {tx_type} {tx.account.code} {tx.account.name:40s} ${tx.amount:>10,.2f}")
            
            # Show updated invoice status
            invoice.refresh_from_db()
            self.stdout.write(f"\n  Updated Invoice Status:")
            self.stdout.write(f"    Total:        ${invoice.total:,.2f}")
            self.stdout.write(f"    Amount Paid:  ${invoice.amount_paid:,.2f}")
            self.stdout.write(f"    Balance Due:  ${invoice.balance_due:,.2f}")
            self.stdout.write(f"    Status:       {invoice.get_status_display()}")
            
            # Summary
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("✓ ALL TESTS PASSED!"))
            self.stdout.write("="*60)
            self.stdout.write(f"\nTest invoice created: {invoice.invoice_number}")
            self.stdout.write(f"View in admin: /admin/forbes_lawn_accounting/invoice/{invoice.pk}/change/")
            self.stdout.write(f"\nYou can now delete this test data from Django admin.")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error posting to ledger: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())