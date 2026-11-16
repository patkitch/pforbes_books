"""Posted-only trial balance for the accounting test ledger."""
from decimal import Decimal

from .models import Account
from .reporting import account_balances, ZERO


def trial_balance(as_of):
    """Direct ledger balances once per account; avoid parent roll-up duplication."""
    raw = account_balances(end=as_of)
    rows = []
    total_debits = ZERO
    total_credits = ZERO
    for account in Account.objects.order_by("number"):
        balance = raw.get(account.pk, ZERO)
        if balance == ZERO:
            continue
        debit = balance if balance > 0 else ZERO
        credit = -balance if balance < 0 else ZERO
        rows.append({"account": account, "debit": debit, "credit": credit})
        total_debits += debit
        total_credits += credit
    return {
        "rows": rows, "debits": total_debits, "credits": total_credits,
        "difference": total_debits - total_credits,
        "balanced": total_debits == total_credits, "as_of": as_of,
    }
