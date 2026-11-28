"""Read-only accounting home and report directory for the local test ledger."""
from datetime import date
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone

from .models import Account, JournalEntry
from .reporting import account_balances, profit_and_loss
from .period_controls import LEDGER_START


def _display_date():
    """Show existing future-dated test records while the local test ledger is being developed."""
    today = timezone.localdate()
    latest = JournalEntry.objects.filter(status="posted").aggregate(
        most_recent=Max("date")
    )["most_recent"]
    return max(today, LEDGER_START, latest or LEDGER_START)


@staff_member_required(login_url="/admin/login/")
def dashboard(request):
    end = _display_date()
    start = date(end.year, 1, 1)
    report = profit_and_loss(start, end)
    totals = report["totals"]
    raw = account_balances(end=end)
    # Bank/cash balances only: exclude credit cards, receivables, equipment, etc.
    bank_accounts = Account.objects.filter(
        account_type="asset", is_active=True
    ).filter(number__startswith="10")
    bank_total = sum((raw.get(a.pk, Decimal("0.00")) for a in bank_accounts), Decimal("0.00"))
    recent = JournalEntry.objects.filter(status="posted").order_by("-date", "-pk")[:6]
    return render(request, "accounting/dashboard.html", {
        "as_of": end, "period_start": start,
        "bank_total": bank_total,
        "income_total": totals["income"] + totals["other_income"],
        "expense_total": totals["expense"] + totals["cogs"] + totals["other_expense"],
        "net_profit": report["net_profit"], "recent": recent,
        "test_dates_ahead": end > timezone.localdate(),
    })


@staff_member_required(login_url="/admin/login/")
def reports_index(request):
    return render(request, "accounting/reports_index.html")
