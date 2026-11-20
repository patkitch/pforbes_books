"""Quarterly cash-basis sales-tax tracking for the local accounting test app.

Rates are provided by the user or payment processor; no rate lookup performed.
"""
from datetime import date
from decimal import Decimal
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from .models import Account, JournalEntry, JournalLine, SalesTaxPayment, SalesTaxRecord
from .period_controls import LEDGER_START, ensure_open_period
from .services import post_entry


TAX_AUTHORITIES = ("2007", "2010")
ZERO = Decimal("0.00")


def tax_authorities():
    return Account.objects.filter(
        number__in=TAX_AUTHORITIES, account_type="liability", is_active=True
    ).order_by("number")


class TaxPaymentForm(forms.Form):
    authority = forms.ModelChoiceField(queryset=Account.objects.none(), label="Tax agency")
    year = forms.IntegerField(min_value=2026, max_value=9999)
    quarter = forms.ChoiceField(choices=[(x, f"Q{x}") for x in (1, 2, 3, 4)])
    amount = forms.DecimalField(min_value=ZERO, max_digits=14, decimal_places=2, label="Tax amount")
    paid_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Payment date")
    bank_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="Bank / Cash account")
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["authority"].queryset = tax_authorities()
        self.fields["bank_account"].queryset = Account.objects.filter(
            is_active=True, account_type="asset"
        ).order_by("number")
        if not self.is_bound:
            self.initial.setdefault("paid_on", timezone.localdate())
            self.initial.setdefault("year", timezone.localdate().year)
            self.initial.setdefault("quarter", (timezone.localdate().month - 1) // 3 + 1)
            self.initial.setdefault("amount", ZERO)

    def clean(self):
        data = super().clean()
        if data.get("paid_on") and data["paid_on"] < LEDGER_START:
            self.add_error("paid_on", "The test ledger begins January 1, 2026.")
        return data


@transaction.atomic
def record_tax_payment(data, *, actor=None):
    """Positive payments post to ledger; zero payments save history only."""
    authority = Account.objects.select_for_update().get(pk=data["authority"].pk)
    bank = Account.objects.select_for_update().get(pk=data["bank_account"].pk)
    if not authority.is_active or authority.number not in TAX_AUTHORITIES or authority.account_type != "liability":
        raise ValidationError("Invalid or inactive tax agency.")
    if not bank.is_active or bank.account_type != "asset":
        raise ValidationError("Choose an active Cash or bank account.")
    amount = data["amount"]
    if amount < ZERO:
        raise ValidationError("Payment cannot be negative.")
    if data["paid_on"] < LEDGER_START:
        raise ValidationError("Payment date is before the start of the test ledger.")
    entry = None
    if amount > ZERO:
        ensure_open_period(data["paid_on"])
        entry = JournalEntry.objects.create(
            date=data["paid_on"], payee=authority.name,
            description=f"Q{data['quarter']} {data['year']} sales tax payment",
            memo=data.get("memo", ""), source="sales_tax", created_by=actor,
        )
        JournalLine.objects.create(entry=entry, account=authority, debit=amount)
        JournalLine.objects.create(entry=entry, account=bank, credit=amount)
        entry = post_entry(entry.pk, actor=actor)
    record = SalesTaxPayment(
        authority=authority, year=data["year"], quarter=int(data["quarter"]),
        amount=amount, paid_on=data["paid_on"], bank_account=bank,
        memo=data.get("memo", ""), journal_entry=entry,
    )
    record.full_clean()
    record.save()
    return record


def quarter_dates(year, quarter):
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = (date(year + 1, 1, 1) - date.resolution) if end_month == 12 else (date(year, end_month + 1, 1) - date.resolution)
    return date(year, start_month, 1), last_day


def kansas_target_dates(year, quarter):
    """Personal planning dates only; not statutory tax deadlines."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError("Quarter must be between 1 and 4.")
    target_year = year + 1 if quarter == 4 else year
    target_month = (4, 7, 10, 1)[quarter - 1]
    return date(target_year, target_month, 5), date(target_year, target_month, 20)


def quarterly_summary(*, year, quarter, authority):
    start, end = quarter_dates(year, quarter)
    # Only records linked to posted entries (or with no ledger journal: gallery
    # tracking) count toward the quarterly sale totals.
    rows = SalesTaxRecord.objects.filter(sale_date__range=(start, end)).filter(
        journal_entry__isnull=True
    ) | SalesTaxRecord.objects.filter(
        sale_date__range=(start, end), journal_entry__status="posted"
    )
    rows = rows.filter(authority=authority)
    totals = rows.aggregate(
        sales=Sum("sale_amount"), taxable=Sum("taxable_amount"), tax=Sum("tax_collected")
    )
    payments = SalesTaxPayment.objects.filter(
        authority=authority, year=year, quarter=quarter
    ).select_related("bank_account").order_by("paid_on", "pk")
    paid = sum((item.amount for item in payments), ZERO)
    # Breakdown uses the free-text location recorded with each sale. These are
    # NOT tax-jurisdiction allocations and should not be presented as such.
    locations = [
        {
            "name": item["jurisdiction"].strip() or "Location not specified",
            "count": item["sale_count"],
            "taxable": item["taxable"] or ZERO,
            "collected": item["collected"] or ZERO,
        }
        for item in rows.values("jurisdiction").annotate(
            sale_count=Count("pk"),
            taxable=Sum("taxable_amount"),
            collected=Sum("tax_collected"),
        ).order_by("jurisdiction")
    ]
    tax = totals["tax"] or ZERO
    return {
        "year": year, "quarter": quarter, "start": start, "end": end,
        "total_sales": totals["sales"] or ZERO,
        "taxable_sales": totals["taxable"] or ZERO,
        "nontaxable_sales": (totals["sales"] or ZERO) - (totals["taxable"] or ZERO),
        "tax_collected": tax, "paid": paid, "remaining": tax - paid,
        "payments": payments,
        "locations": locations,
        "prepare_date": kansas_target_dates(year, quarter)[0] if authority.number == "2007" else None,
        "target_date": kansas_target_dates(year, quarter)[1] if authority.number == "2007" else None,
        "record_count": rows.count(),
    }


@staff_member_required(login_url="/admin/login/")
def tax_dashboard(request):
    now = timezone.localdate()
    form = TaxPaymentForm(request.POST or None)
    year = now.year
    quarter = (now.month - 1) // 3 + 1
    raw_year = request.GET.get("year")
    raw_quarter = request.GET.get("quarter")
    if raw_year and raw_year.isdigit() and 2026 <= int(raw_year) <= 9999:
        year = int(raw_year)
    if raw_quarter in ("1", "2", "3", "4"):
        quarter = int(raw_quarter)
    authorities = list(tax_authorities())
    reports = [
        {"account": a, "summary": quarterly_summary(year=year, quarter=quarter, authority=a)}
        for a in authorities
    ]
    if request.method == "POST" and form.is_valid():
        try:
            record_tax_payment(form.cleaned_data, actor=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect(f"{request.path}?year={form.cleaned_data['year']}&quarter={form.cleaned_data['quarter']}")
    return render(request, "accounting/sales_tax.html", {
        "form": form, "reports": reports, "year": year, "quarter": quarter,
        "year_options": range(2026, max(2027, now.year) + 2),
        "quarters": (1, 2, 3, 4),
    })
