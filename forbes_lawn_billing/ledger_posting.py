from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django_ledger.models import (
    AccountModel,
    LedgerModel,
    JournalEntryModel,
    TransactionModel,
)

from forbes_lawn_billing.models import InvoicePayment
from .models import Invoice


def get_account(entity, code: str) -> AccountModel:
    return AccountModel.objects.get(
        coa_model__entity=entity,
        code=code,
    )


@transaction.atomic
def post_open_invoice_to_ledger(invoice: Invoice, ledger: LedgerModel) -> JournalEntryModel | None:
    """
    Create & post the JE for an OPEN invoice.

      - DR 1010 Accounts Receivable       (sum of VALID line amounts + tax)
      - CR revenue accounts (per VALID line)
      - CR 2011 Kansas Dept of Revenue    (tax amount)

    IMPORTANT SAFETY:
      If there are NO valid revenue lines (missing item_model / missing earnings_account),
      we return None so we do NOT create a "tax-only" JE.
    """
    if invoice.ar_journal_entry_id:
        return invoice.ar_journal_entry

    entity = invoice.entity
    if entity is None:
        raise ValueError("Invoice must have an entity set before posting to ledger.")

    if ledger.entity_id != entity.uuid:
        raise ValueError("Ledger entity does not match invoice.entity.")

    ar_acct = get_account(entity, "1010")   # Accounts Receivable
    tax_acct = get_account(entity, "2011")  # Sales tax liability

    all_lines = list(invoice.lines.all())

    valid_lines: list = []
    for line in all_lines:
        if not line.line_amount or line.line_amount <= Decimal("0.00"):
            continue
        if not line.item_model:
            continue
        earnings_account = line.item_model.earnings_account
        if earnings_account is None:
            continue
        valid_lines.append(line)

    # If nothing valid, do NOT post anything (prevents "tax-only" JEs)
    if not valid_lines:
        return None

    lines_total = sum((l.line_amount for l in valid_lines), Decimal("0.00"))
    tax_amount = (invoice.tax_amount or Decimal("0.00")).quantize(Decimal("0.01"))
    ar_amount = (lines_total + tax_amount).quantize(Decimal("0.01"))

    if ar_amount == Decimal("0.00"):
        return None

    invoice_dt = datetime.combine(invoice.invoice_date, datetime.min.time())
    invoice_ts = timezone.make_aware(invoice_dt, timezone.get_current_timezone())

    je = JournalEntryModel.objects.create(
        ledger=ledger,
        timestamp=invoice_ts,
        description=f"Invoice {invoice.invoice_number} – {invoice.customer_name}",
        origin="forbes_lawn_invoice_open",
        posted=False,
        locked=False,
    )

    TransactionModel.objects.create(
        journal_entry=je,
        account=ar_acct,
        tx_type=TransactionModel.DEBIT,
        amount=ar_amount,
        description=f"AR for invoice {invoice.invoice_number}",
    )

    for line in valid_lines:
        earnings_account = line.item_model.earnings_account
        TransactionModel.objects.create(
            journal_entry=je,
            account=earnings_account,
            tx_type=TransactionModel.CREDIT,
            amount=line.line_amount,
            description=line.description or line.item_name,
        )

    if tax_amount > Decimal("0.00"):
        TransactionModel.objects.create(
            journal_entry=je,
            account=tax_acct,
            tx_type=TransactionModel.CREDIT,
            amount=tax_amount,
            description=f"Sales tax – invoice {invoice.invoice_number}",
        )

    je.mark_as_posted(
        commit=True,
        verify=True,
        force_lock=True,
        raise_exception=True,
    )

    invoice.ar_journal_entry = je
    invoice.save(update_fields=["ar_journal_entry"])

    return je


@transaction.atomic
def post_invoice_payment_to_ledger(
    invoice_payment: InvoicePayment,
    ledger: LedgerModel,
) -> JournalEntryModel:
    """
    Create & post JE for a payment:

      - DR 1024 Payments to Deposit
      - CR 1010 Accounts Receivable
    """
    if invoice_payment.payment_journal_entry_id:
        return invoice_payment.payment_journal_entry

    invoice = invoice_payment.invoice
    entity = invoice.entity

    if entity is None:
        raise ValueError("Invoice must have an entity set before posting payment to ledger.")

    if ledger.entity_id != entity.uuid:
        raise ValueError("Ledger entity does not match invoice.entity.")

    ar_acct = get_account(entity, "1010")        # Accounts Receivable
    payments_acct = get_account(entity, "1024")  # Payments to Deposit

    amount = invoice_payment.amount

    payment_dt = datetime.combine(invoice_payment.payment_date, datetime.min.time())
    payment_ts = timezone.make_aware(payment_dt, timezone.get_current_timezone())

    je = JournalEntryModel.objects.create(
        ledger=ledger,
        timestamp=payment_ts,
        description=f"Payment for invoice {invoice.invoice_number}",
        origin="forbes_lawn_invoice_payment",
        posted=False,
        locked=False,
    )

    TransactionModel.objects.create(
        journal_entry=je,
        account=payments_acct,
        tx_type=TransactionModel.DEBIT,
        amount=amount,
        description=f"Payment applied to invoice {invoice.invoice_number}",
    )

    TransactionModel.objects.create(
        journal_entry=je,
        account=ar_acct,
        tx_type=TransactionModel.CREDIT,
        amount=amount,
        description=f"Clear AR for invoice {invoice.invoice_number}",
    )

    je.mark_as_posted(
        commit=True,
        verify=True,
        force_lock=True,
        raise_exception=True,
    )

    invoice_payment.payment_journal_entry = je
    invoice_payment.save(update_fields=["payment_journal_entry"])

    return je
