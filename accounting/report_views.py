"""Read-only financial reports. Financial statements use posted entries only."""
from datetime import date

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .reporting import balance_sheet, profit_and_loss


class ProfitLossDates(forms.Form):
    start = forms.DateField(
        initial=date(2027, 1, 1),
        widget=forms.DateInput(attrs={"type": "date"}),
        label="From",
    )
    end = forms.DateField(
        initial=date(2027, 12, 31),
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Through",
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and start < date(2027, 1, 1):
            self.add_error("start", "The ledger starts January 1, 2027.")
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
        if value < date(2027, 1, 1):
            raise forms.ValidationError("The ledger starts January 1, 2027.")
        return value


@staff_member_required(login_url="/admin/login/")
def profit_loss_view(request):
    form = ProfitLossDates(request.GET if request.GET else {"start": "2027-01-01", "end": "2027-12-31"})
    data = profit_and_loss(**form.cleaned_data) if form.is_valid() else None
    return render(request, "accounting/profit_loss.html", {"form": form, "report": data})


@staff_member_required(login_url="/admin/login/")
def balance_sheet_view(request):
    form = BalanceSheetDate(request.GET if request.GET else {"as_of": "2027-12-31"})
    data = balance_sheet(form.cleaned_data["as_of"]) if form.is_valid() else None
    return render(request, "accounting/balance_sheet.html", {"form": form, "report": data})
