# books/services/posting.py
from decimal import Decimal
from django.utils import timezone

# Import django-ledger models locally so swap is possible later
from django_ledger.models.entity import EntityModel
from django_ledger.models import (
    AccountModel,
    ChartOfAccountModel,
    LedgerModel,
    JournalEntryModel,
)
from django_ledger.models.transactions import TransactionModel

def _money(val) -> Decimal:
    # Accept cents (int) or Decimal dollars; normalize to Decimal dollars here
    return Decimal(val) / Decimal("100") if isinstance(val, int) else Decimal(val)

def post_invoice(*, entity: EntityModel, ledger: LedgerModel,
                 ar_code: str, sales_code: str, tax_code: str,
                 subtotal, tax, memo: str = "") -> JournalEntryModel:
    """
    DR AR = subtotal + tax
    CR Sales = subtotal
    CR Sales Tax Payable = tax
    """
    subtotal = _money(subtotal)
    tax = _money(tax)
    total = subtotal + tax

    ar    = AccountModel.objects.get(coa__entity=entity, code=ar_code)
    sales = AccountModel.objects.get(coa__entity=entity, code=sales_code)
    taxp  = AccountModel.objects.get(coa__entity=entity, code=tax_code)

    je = JournalEntryModel.objects.create(
        entity=entity,
        ledger=ledger,
        occurred_at=timezone.now().date(),
        memo=memo or "Invoice"
    )
    TransactionModel.objects.create(entry=je, account=ar,    debit=total,   credit=Decimal("0.00"), memo="AR")
    TransactionModel.objects.create(entry=je, account=sales, debit=Decimal("0.00"), credit=subtotal, memo="Revenue")
    TransactionModel.objects.create(entry=je, account=taxp,  debit=Decimal("0.00"), credit=tax,      memo="Sales Tax")

    # If django-ledger requires a commit/dispatch step in your version, call it here.
    return je

def post_payment(*, entity: EntityModel, ledger: LedgerModel,
                 cash_code: str, fee_code: str, ar_code: str,
                 gross, fee=0, memo: str = "") -> JournalEntryModel:
    """
    DR Cash = gross - fee
    DR Stripe Fees = fee
    CR AR = gross
    """
    gross = _money(gross)
    fee   = _money(fee)
    net   = gross - fee

    cash  = AccountModel.objects.get(coa__entity=entity, code=cash_code)
    fees  = AccountModel.objects.get(coa__entity=entity, code=fee_code)
    ar    = AccountModel.objects.get(coa__entity=entity, code=ar_code)

    je = JournalEntryModel.objects.create(
        entity=entity,
        ledger=ledger,
        occurred_at=timezone.now().date(),
        memo=memo or "Payment"
    )
    if net != 0:
        TransactionModel.objects.create(entry=je, account=cash, debit=net, credit=0, memo="Cash/Undeposited")
    if fee != 0:
        TransactionModel.objects.create(entry=je, account=fees, debit=fee, credit=0, memo="Stripe Fee")
    TransactionModel.objects.create(entry=je, account=ar, debit=0, credit=gross, memo="AR clear")

    return je

def post_cogs(*, entity: EntityModel, ledger: LedgerModel,
              inv_code: str, cogs_code: str, cost, memo: str = "") -> JournalEntryModel:
    """
    DR COGS = cost
    CR Inventory = cost
    """
    cost = _money(cost)
    inv  = AccountModel.objects.get(coa__entity=entity, code=inv_code)
    cogs = AccountModel.objects.get(coa__entity=entity, code=cogs_code)

    je = JournalEntryModel.objects.create(
        entity=entity,
        ledger=ledger,
        occurred_at=timezone.now().date(),
        memo=memo or "COGS"
    )
    TransactionModel.objects.create(entry=je, account=cogs, debit=cost, credit=0, memo="COGS")
    TransactionModel.objects.create(entry=je, account=inv,  debit=0,    credit=cost, memo="Inventory")

    return je
