"""Read-only financial reports. Financial statements use posted entries only."""
from datetime import date

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Max
from django.utils import timezone

from .models import JournalEntry
from .period_controls import LEDGER_START

from .reporting import balance_sheet, profit_and_loss


def default_report_end():
    """Use current year unless future-dated local test postings are present."""
    latest = JournalEntry.objects.filter(status="posted").aggregate(
        most_recent=Max("date")
    )["most_recent"]
    return max(LEDGER_START, timezone.localdate(), latest or LEDGER_START)


def default_profit_loss_dates():
    end = default_report_end()
    return {"start": date(end.year, 1, 1).isoformat(), "end": end.isoformat()}


def default_balance_sheet_date():
    return {"as_of": default_report_end().isoformat()}


class ProfitLossDates(forms.Form):
    start = forms.DateField(
        initial=LEDGER_START,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="From",
    )
    end = forms.DateField(
        initial=default_report_end,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Through",
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and start < LEDGER_START:
            self.add_error("start", "The ledger starts January 1, 2026.")
        if start and end and start > end:
            self.add_error("end", "The end date must be on or after the start date.")
        return cleaned


class BalanceSheetDate(forms.Form):
    as_of = forms.DateField(
        initial=date(2027, 12, 31),
        widget=forms.DateInput(attrs={"type": "date"}),
        label="As of",
    )

    def clean_as_of(self):
        value = self.cleaned_data["as_of"]
        if value < LEDGER_START:
            raise forms.ValidationError("The ledger starts January 1, 2026.")
        return value


@staff_member_required(login_url="/admin/login/")
def profit_loss_view(request):
    form = ProfitLossDates(request.GET if request.GET else default_profit_loss_dates())
    data = profit_and_loss(**form.cleaned_data) if form.is_valid() else None
    return render(request, "accounting/profit_loss.html", {"form": form, "report": data})


@staff_member_required(login_url="/admin/login/")
def balance_sheet_view(request):
    form = BalanceSheetDate(request.GET if request.GET else default_balance_sheet_date())
    data = balance_sheet(form.cleaned_data["as_of"]) if form.is_valid() else None
    return render(request, "accounting/balance_sheet.html", {"form": form, "report": data})
