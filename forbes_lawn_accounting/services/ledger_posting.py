"""
Ledger Posting Service for Forbes Lawn Accounting

This service handles all journal entry creation and posting to Django Ledger.

Key Principles:
1. Each invoice gets its own unique Ledger
2. Each payment gets its own unique Ledger  
3. Each bank deposit gets its own unique Ledger (Phase 2)
4. Each vendor bill gets its own unique Ledger (Phase 3)

Posting Logic:
- Invoice:  DR 1010 AR, CR 4024/4025 Revenue, CR 2024 Sales Tax
- Payment:  DR 1024 Payments to Deposit, CR 1010 AR
- Deposit:  DR 1001 Cash, DR 6128 Jobber Fees, CR 1024 Payments to Deposit (Phase 2)
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django_ledger.models.entity import EntityModel
from django_ledger.models.ledger import LedgerModel
from django_ledger.models.journal_entry import JournalEntryModel
from django_ledger.models.chart_of_accounts import ChartOfAccountModel


class LedgerPostingService:
    """
    Service for posting Forbes Lawn transactions to Django Ledger.
    
    Usage:
        entity = EntityModel.objects.get(slug='forbes-lawn-spraying-llc-dev-d6qyx55c')
        poster = LedgerPostingService(entity)
        poster.post_invoice_to_ledger(invoice)
    """
    
    def __init__(self, entity: EntityModel):
        """
        Initialize the posting service for a specific entity.
        
        Args:
            entity: The Forbes Lawn entity to post transactions for
        """
        self.entity = entity
        
        # Get the COA for this entity
        # EntityModel has a reverse relation to ChartOfAccountModel
        from django_ledger.models.chart_of_accounts import ChartOfAccountModel
        
        try:
            # Get the default COA for this entity
            self.coa = ChartOfAccountModel.objects.filter(entity=entity).first()
            
            if not self.coa:
                raise ValueError(
                    f"Entity '{entity.name}' does not have a Chart of Accounts. "
                    "Please create a COA for this entity first."
                )
        except Exception as e:
            raise ValueError(
                f"Error getting COA for entity '{entity.name}': {e}"
            )
    
    def _get_account(self, code: str) -> ChartOfAccountModel:
        """
        Get a COA account by code (e.g., '1010' for AR).
        
        Args:
            code: The account code (e.g., '1010', '4024', '2024')
            
        Returns:
            ChartOfAccountModel instance (the actual account)
            
        Raises:
            ValueError: If account code doesn't exist
        """
        from django_ledger.models.accounts import AccountModel
        
        try:
            # AccountModel has the 'code' field and links to the COA
            account = AccountModel.objects.get(
                coa_model=self.coa,
                code=code
            )
            return account
        except AccountModel.DoesNotExist:
            raise ValueError(
                f"Account code '{code}' not found in COA '{self.coa.name}'. "
                f"Please verify the account exists in Django Ledger admin."
            )
    
    @transaction.atomic
    def post_invoice_to_ledger(self, invoice):
        """
        Post an invoice to the ledger.
        
        Creates:
        - A new Ledger for this invoice
        - A Journal Entry with transactions:
          DR 1010 Accounts Receivable     [total]
          CR 4024 Service Income-Taxable  [taxable amount]
          CR 4025 Service Income-NonTax   [non-taxable amount]
          CR 2024 Sales Tax to Pay        [tax amount]
        
        Args:
            invoice: Invoice model instance
            
        Returns:
            The created JournalEntryModel
            
        Raises:
            ValueError: If invoice already posted or has invalid data
        """
        from forbes_lawn_accounting.models import Invoice
        
        if not isinstance(invoice, Invoice):
            raise ValueError("Must provide an Invoice instance")
        
        if invoice.posted_to_ledger:
            raise ValueError(
                f"Invoice {invoice.invoice_number} is already posted to ledger. "
                f"Posted at: {invoice.posted_at}"
            )
        
        if invoice.total <= 0:
            raise ValueError(
                f"Invoice {invoice.invoice_number} has zero or negative total. "
                f"Cannot post to ledger."
            )
        
        # Step 1: Create a unique Ledger for this invoice
        ledger = LedgerModel.objects.create(
            entity=self.entity,
            name=f"Invoice: {invoice.invoice_number}",
            posted=True,
        )
        
        # Step 2: Create the Journal Entry in that ledger
        je = JournalEntryModel.objects.create(
            ledger=ledger,
            description=f"Invoice {invoice.invoice_number} - {invoice.customer.name}",
            # Django Ledger JournalEntry doesn't have 'date' field - it uses timestamp
            # origin='forbes_lawn_invoice',  # Also might not exist
        )
        
        # NOTE: Don't lock yet - need to add transactions first!
        
        # Step 3: Create the DR/CR transactions
        from django_ledger.models.transactions import TransactionModel
        
        # DR: Accounts Receivable (1010)
        TransactionModel.objects.create(
            journal_entry=je,
            account=self._get_account('1010'),
            tx_type='debit',
            amount=invoice.total,
            description=f"Invoice {invoice.invoice_number}",
        )
        
        # Calculate taxable vs non-taxable revenue
        taxable_revenue = Decimal('0.00')
        nontaxable_revenue = Decimal('0.00')
        
        for line in invoice.lines.all():
            if line.taxable:
                taxable_revenue += line.amount
            else:
                nontaxable_revenue += line.amount
        
        # Apply discount proportionally (if any)
        if invoice.discount_amount > 0:
            total_revenue = taxable_revenue + nontaxable_revenue
            if total_revenue > 0:
                discount_ratio = invoice.discount_amount / total_revenue
                taxable_revenue = (taxable_revenue * (1 - discount_ratio)).quantize(Decimal('0.01'))
                nontaxable_revenue = (nontaxable_revenue * (1 - discount_ratio)).quantize(Decimal('0.01'))
        
        # CR: Taxable Service Income (4024)
        if taxable_revenue > 0:
            TransactionModel.objects.create(
                journal_entry=je,
                account=self._get_account('4024'),
                tx_type='credit',
                amount=taxable_revenue,
                description="Taxable services",
            )
        
        # CR: Non-Taxable Service Income (4025)
        if nontaxable_revenue > 0:
            TransactionModel.objects.create(
                journal_entry=je,
                account=self._get_account('4025'),
                tx_type='credit',
                amount=nontaxable_revenue,
                description="Non-taxable services",
            )
        
        # CR: Sales Tax Payable (2011 Kansas Department of Revenue)
        if invoice.tax_amount > 0:
            TransactionModel.objects.create(
                journal_entry=je,
                account=self._get_account('2011'),  # Changed from 2024 to 2011
                tx_type='credit',
                amount=invoice.tax_amount,
                description="Sales tax collected",
            )
        
        # Step 4: NOW lock and post the journal entry (after all transactions added)
        je.locked = True
        je.posted = True
        je.save()
        
        # Step 5: Mark invoice as posted
        invoice.ar_journal_entry = je
        invoice.posted_to_ledger = True
        invoice.posted_at = timezone.now()
        invoice.save(update_fields=['ar_journal_entry', 'posted_to_ledger', 'posted_at'])
        
        return je
    
    @transaction.atomic
    def post_payment_to_ledger(self, payment):
        """
        Post a payment to the ledger.
        
        Creates:
        - A new Ledger for this payment
        - A Journal Entry with transactions:
          DR 1024 Payments to Deposit  [amount]
          CR 1010 Accounts Receivable  [amount]
        
        Args:
            payment: InvoicePayment model instance
            
        Returns:
            The created JournalEntryModel
            
        Raises:
            ValueError: If payment already posted or has invalid data
        """
        from forbes_lawn_accounting.models import InvoicePayment
        
        if not isinstance(payment, InvoicePayment):
            raise ValueError("Must provide an InvoicePayment instance")
        
        if payment.posted_to_ledger:
            raise ValueError(
                f"Payment on invoice {payment.invoice.invoice_number} is already posted. "
                f"Posted at: {payment.posted_at}"
            )
        
        if payment.amount <= 0:
            raise ValueError(
                f"Payment has zero or negative amount. Cannot post to ledger."
            )
        
        # Step 1: Create a unique Ledger for this payment
        ledger = LedgerModel.objects.create(
            entity=self.entity,
            name=f"Payment: Invoice {payment.invoice.invoice_number}",
            posted=True,
        )
        
        # Step 2: Create the Journal Entry in that ledger
        je = JournalEntryModel.objects.create(
            ledger=ledger,
            description=f"Payment on Invoice {payment.invoice.invoice_number} - {payment.invoice.customer.name}",
            # Django Ledger JournalEntry doesn't have 'date' field - it uses timestamp
        )
        
        # NOTE: Don't lock yet - need to add transactions first!
        
        # Step 3: Create the DR/CR transactions
        from django_ledger.models.transactions import TransactionModel
        
        # DR: Payments to Deposit (1024)
        TransactionModel.objects.create(
            journal_entry=je,
            account=self._get_account('1024'),
            tx_type='debit',
            amount=payment.amount,
            description=f"Payment - {payment.get_payment_method_display()}",
        )
        
        # CR: Accounts Receivable (1010)
        TransactionModel.objects.create(
            journal_entry=je,
            account=self._get_account('1010'),
            tx_type='credit',
            amount=payment.amount,
            description=f"Invoice {payment.invoice.invoice_number}",
        )
        
        # Step 4: NOW lock and post the journal entry (after all transactions added)
        je.locked = True
        je.posted = True
        je.save()
        
        # Step 5: Mark payment as posted
        payment.journal_entry = je
        payment.posted_to_ledger = True
        payment.posted_at = timezone.now()
        payment.save(update_fields=['journal_entry', 'posted_to_ledger', 'posted_at'])
        
        # Step 5: Update invoice totals
        payment.invoice.recompute_totals()
        
        return je
    
    def get_ledger_for_invoice(self, invoice):
        """
        Get the ledger for a specific invoice (if it exists).
        
        Args:
            invoice: Invoice model instance
            
        Returns:
            LedgerModel or None
        """
        if invoice.ar_journal_entry:
            return invoice.ar_journal_entry.ledger
        return None
    
    def get_ledger_for_payment(self, payment):
        """
        Get the ledger for a specific payment (if it exists).
        
        Args:
            payment: InvoicePayment model instance
            
        Returns:
            LedgerModel or None
        """
        if payment.journal_entry:
            return payment.journal_entry.ledger
        return None
    
    def verify_posting(self, invoice):
        """
        Verify that an invoice was posted correctly.
        
        Checks:
        - Ledger exists
        - Journal entry exists
        - Transactions balance (DR = CR)
        - Transaction amounts match invoice amounts
        
        Args:
            invoice: Invoice model instance
            
        Returns:
            dict with verification results
        """
        results = {
            'is_posted': invoice.posted_to_ledger,
            'has_journal_entry': invoice.ar_journal_entry is not None,
            'has_ledger': False,
            'transactions_balance': False,
            'amounts_match': False,
            'errors': []
        }
        
        if not invoice.ar_journal_entry:
            results['errors'].append("No journal entry found")
            return results
        
        je = invoice.ar_journal_entry
        results['has_ledger'] = je.ledger is not None
        
        # Check if transactions balance
        from django.db.models import Sum, Q
        from django_ledger.models.transactions import TransactionModel
        
        debits = TransactionModel.objects.filter(
            journal_entry=je,
            tx_type='debit'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        credits = TransactionModel.objects.filter(
            journal_entry=je,
            tx_type='credit'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        results['debit_total'] = debits
        results['credit_total'] = credits
        results['transactions_balance'] = (debits == credits)
        
        if debits != credits:
            results['errors'].append(f"Debits ({debits}) != Credits ({credits})")
        
        # Check if amounts match invoice
        results['amounts_match'] = (debits == invoice.total)
        
        if debits != invoice.total:
            results['errors'].append(f"Journal entry total ({debits}) != Invoice total ({invoice.total})")
        
        return results


class LedgerPostingError(Exception):
    """Custom exception for ledger posting errors."""
    pass