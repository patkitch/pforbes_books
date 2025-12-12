# forbes_lawn_billing/ledger_posting.py

from decimal import Decimal
from datetime import datetime
from typing import Optional
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_ledger.models import (
    AccountModel,
    LedgerModel,
    JournalEntryModel,
    TransactionModel,
    EntityModel,
)

from forbes_lawn_billing.models import InvoicePayment
from django_ledger.io.io_library import IOBluePrint
from .models import Invoice


def get_account(entity, code: str) -> AccountModel:
    """
    Helper to fetch an AccountModel for a given entity + account code.
    Adjust the lookup if you use more than one COA per entity.
    """
    return AccountModel.objects.get(
        coa_model__entity=entity,
        code=code,
    )


@transaction.atomic
def post_open_invoice_to_ledger(invoice: Invoice, ledger: LedgerModel) -> JournalEntryModel | None:
    """
    Create & post the JE for an OPEN invoice.

    Pattern:

      - DR 1010 Accounts Receivable       (sum of VALID line amounts + tax)
      - CR revenue accounts (per VALID line)
      - CR 2011 Kansas Dept of Revenue    (tax amount)

    Notes:
      • We derive AR from the detail of VALID lines only:
            AR = sum(valid line_amount) + tax_amount
        where "valid" means: item_model + earnings_account + positive amount.
      • Any lines missing item_model or earnings_account are skipped from BOTH
        the revenue credits and the AR amount so the JE stays balanced.
    """
    # Already posted? Just return the existing JE.
    if invoice.ar_journal_entry_id:
        return invoice.ar_journal_entry

    entity = invoice.entity
    if entity is None:
        raise ValueError("Invoice must have an entity set before posting to ledger.")

    # Safety: ledger must belong to same EntityModel
    if ledger.entity_id != entity.uuid:
        raise ValueError("Ledger entity does not match invoice.entity.")

    # 1) Get key accounts
    ar_acct = get_account(entity, "1010")   # Accounts Receivable
    tax_acct = get_account(entity, "2011")  # Kansas Department of Revenue (sales tax liability)

    # 2) Compute detail totals from VALID line items only
    all_lines = list(invoice.lines.all())

    valid_lines: list = []
    for line in all_lines:
        if not line.line_amount or line.line_amount <= Decimal("0.00"):
            continue
        if not line.item_model:
            # No item_model: skip this line entirely from posting
            continue
        earnings_account = line.item_model.earnings_account
        if earnings_account is None:
            # No earnings_account: skip this line as well
            continue
        # If we get here, the line is valid for posting
        valid_lines.append(line)

    lines_total = sum(
        (l.line_amount for l in valid_lines),
        Decimal("0.00"),
    )
    tax_amount = (invoice.tax_amount or Decimal("0.00")).quantize(Decimal("0.01"))

    # AR is defined from VALID detail so JE always balances:
    #   AR = sum(valid line_amount) + tax_amount
    ar_amount = (lines_total + tax_amount).quantize(Decimal("0.01"))

    if ar_amount == Decimal("0.00"):
        # Nothing to post
        return None

    # 3) Create the Journal Entry with a timezone-aware timestamp
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

    # 4) DR AR with full detail total (valid lines + tax)
    TransactionModel.objects.create(
        journal_entry=je,
        account=ar_acct,
        tx_type=TransactionModel.DEBIT,
        amount=ar_amount,
        description=f"AR for invoice {invoice.invoice_number}",
    )

    # 5) CR revenue per VALID line (pre-tax)
    for line in valid_lines:
        earnings_account = line.item_model.earnings_account

        TransactionModel.objects.create(
            journal_entry=je,
            account=earnings_account,
            tx_type=TransactionModel.CREDIT,
            amount=line.line_amount,
            description=line.description or line.item_name,
        )

    # 6) CR sales tax liability
    if tax_amount > Decimal("0.00"):
        TransactionModel.objects.create(
            journal_entry=je,
            account=tax_acct,
            tx_type=TransactionModel.CREDIT,
            amount=tax_amount,
            description=f"Sales tax – invoice {invoice.invoice_number}",
        )

    # 7) Verify + lock + post
    je.mark_as_posted(
        commit=True,
        verify=True,
        force_lock=True,
        raise_exception=True,
    )

    # 8) Link JE back to the invoice
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

    Revenue & tax were already recognized on the OPEN-invoice JE.
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

    # Make timestamp timezone-aware from payment_date (a DateField)
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

    # DR Payments to Deposit
    TransactionModel.objects.create(
        journal_entry=je,
        account=payments_acct,
        tx_type=TransactionModel.DEBIT,
        amount=amount,
        description=f"Payment applied to invoice {invoice.invoice_number}",
    )

    # CR AR
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
