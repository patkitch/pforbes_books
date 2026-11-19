"""Posted-only, zero-opening-balance financial reports for the 2026-start local test ledger.

Use debit/credit arithmetic from journal lines. Do not include drafts.
Parent totals roll up each account once without duplicating child postings.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from .models import Account, JournalLine

ZERO = Decimal("0.00")
DEBIT_NORMAL = {"asset", "cogs", "expense", "other_expense"}
PL_TYPES = ("income", "cogs", "expense", "other_income", "other_expense")


def account_balances(*, start=None, end=None):
    """Balances keyed by account primary key; only posted lines in the requested window."""
    lines = JournalLine.objects.filter(entry__status="posted")
    if start is not None:
        lines = lines.filter(entry__date__gte=start)
    if end is not None:
        lines = lines.filter(entry__date__lte=end)
    totals = lines.values("account_id").annotate(
        debit_total=Sum("debit"), credit_total=Sum("credit")
    )
    return {
        row["account_id"]: (row["debit_total"] - row["credit_total"])
        for row in totals
    }


def _tree_rollups(accounts, raw):
    """Compute direct and consolidated natural-side balances by account."""
    by_id = {account.pk: account for account in accounts}
    children = defaultdict(list)
    for account in accounts:
        if account.parent_id in by_id:
            children[account.parent_id].append(account.pk)
    direct = {}
    for account in accounts:
        debit_minus_credit = raw.get(account.pk, ZERO)
        direct[account.pk] = debit_minus_credit if account.account_type in DEBIT_NORMAL else -debit_minus_credit
    rolled = {}
    def total(pk, path):
        if pk in path:
            raise ValueError("Account hierarchy contains a cycle.")
        if pk not in rolled:
            rolled[pk] = direct[pk] + sum(
                (total(child_id, path | {pk}) for child_id in children[pk]), ZERO
            )
        return rolled[pk]
    for account in accounts:
        total(account.pk, set())
    return direct, rolled


def profit_and_loss(start, end):
    if start > end:
        raise ValueError("Start date must not be later than end date.")
    accounts = list(Account.objects.select_related("parent").order_by("number"))
    raw = account_balances(start=start, end=end)
    direct, rolled = _tree_rollups(accounts, raw)
    groups = []
    totals = {}
    for account_type, title in [
        ("income", "Income"),
        ("cogs", "Cost of Goods Sold"),
        ("expense", "Operating Expenses"),
        ("other_income", "Other Income"),
        ("other_expense", "Other Expenses"),
    ]:
        rows = [
            {"account": a, "amount": direct[a.pk]}
            for a in accounts if a.account_type == account_type and direct[a.pk] != ZERO
        ]
        # Show 4010 as a subtotal of its five sales children, not another
        # income line that would double-count those same transactions.
        if account_type == "income":
            sales_parent = next(
                (a for a in accounts if a.number == "4010" and a.name == "Sales Income"),
                None,
            )
            if sales_parent:
                subtotal = rolled[sales_parent.pk]
                if subtotal != ZERO:
                    sales_row = {
                        "account": sales_parent, "amount": subtotal,
                        "is_subtotal": True,
                    }
                    # Place subtotal immediately after the last sales child.
                    children_positions = [
                        idx for idx, row in enumerate(rows)
                        if row["account"].parent_id == sales_parent.pk
                    ]
                    position = max(children_positions) + 1 if children_positions else len(rows)
                    rows.insert(position, sales_row)
        value = sum((r["amount"] for r in rows if not r.get("is_subtotal")), ZERO)
        totals[account_type] = value
        groups.append({"title": title, "key": account_type, "rows": rows, "total": value})
    gross_profit = totals["income"] - totals["cogs"]
    operating_profit = gross_profit - totals["expense"]
    net_profit = operating_profit + totals["other_income"] - totals["other_expense"]
    return {
        "groups": groups, "totals": totals, "gross_profit": gross_profit,
        "operating_profit": operating_profit, "net_profit": net_profit,
        "start": start, "end": end,
    }


def balance_sheet(as_of):
    """Lifetime-to-date values, starting from the local ledger's zero opening balances.

    Current earnings are income minus expenses to date; this has NOT implemented
    annual close / retained earnings transfers for later years.
    """
    accounts = list(Account.objects.select_related("parent").order_by("number"))
    raw = account_balances(end=as_of)
    direct, rolled = _tree_rollups(accounts, raw)
    groups = []
    totals = {}
    for account_type, title in [
        ("asset", "Assets"), ("liability", "Liabilities"), ("equity", "Owner's Equity")
    ]:
        rows = [
            {"account": a, "amount": direct[a.pk]}
            for a in accounts if a.account_type == account_type and direct[a.pk] != ZERO
        ]
        value = sum((r["amount"] for r in rows), ZERO)
        totals[account_type] = value
        groups.append({"title": title, "key": account_type, "rows": rows, "total": value})
    earnings = (
        sum((direct[a.pk] for a in accounts if a.account_type in ("income", "other_income")), ZERO)
        - sum((direct[a.pk] for a in accounts if a.account_type in ("cogs", "expense", "other_expense")), ZERO)
    )
    total_equity = totals["equity"] + earnings
    liabilities_and_equity = totals["liability"] + total_equity
    difference = totals["asset"] - liabilities_and_equity
    return {
        "groups": groups, "totals": totals, "earnings": earnings,
        "total_equity": total_equity,
        "liabilities_and_equity": liabilities_and_equity,
        "difference": difference, "balanced": difference == ZERO, "as_of": as_of,
    }
