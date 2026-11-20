"""Guided manual sales with sales tax and optional processor fees.

No Stripe/WooCommerce integration yet. Enter the actual processor amounts,
or supply a researched rate for cash transactions. Only posted sales appear
in the quarterly tax report.
"""
from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Account, JournalEntry, JournalLine, SalesTaxRecord
from .period_controls import LEDGER_START, ensure_open_period
from .sales_tax import tax_authorities, ZERO
from .services import post_entry


CENT = Decimal("0.01")


class TaxableSaleForm(forms.Form):
    source = forms.ChoiceField(
        label="Sale method", choices=SalesTaxRecord.SOURCES[:3]
    )
    sale_date = forms.DateField(
        label="Date paid", widget=forms.DateInput(attrs={"type": "date"})
    )
    description = forms.CharField(max_length=255, label="Description / artwork")
    reference = forms.CharField(
        max_length=180, required=False,
        label="Stripe transaction / order reference (optional)",
        help_text="Use a unique payment or order reference to prevent recording it twice.",
    )
    revenue_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Sales Income account"
    )
    deposit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Received into (Cash or Bank)"
    )
    sale_amount = forms.DecimalField(
        min_value=CENT, max_digits=14, decimal_places=2,
        label="Artwork price before tax"
    )
    taxable_amount = forms.DecimalField(
        min_value=ZERO, max_digits=14, decimal_places=2,
        label="Taxable portion of artwork price"
    )
    authority = forms.ModelChoiceField(
        queryset=Account.objects.none(), required=False,
        label="Tax payable agency (for tax you collect)"
    )
    tax_rate = forms.DecimalField(
        min_value=ZERO, max_value=Decimal("100"),
        max_digits=8, decimal_places=4, required=False,
        label="Tax rate (%) for cash sale",
        help_text="Cash sales: enter the combined percentage from an official rate lookup, e.g. 9.1000 for 9.1%.",
    )
    tax_collected = forms.DecimalField(
        min_value=ZERO, max_digits=14, decimal_places=2, required=False,
        label="Sales tax collected (Stripe amount)",
        help_text="Stripe sales: enter exactly what Stripe charged. Cash sales: leave blank to calculate from the rate.",
    )
    jurisdiction = forms.CharField(
        max_length=160, required=False,
        label="Delivery / pickup location or tax jurisdiction"
    )
    processor_fee = forms.DecimalField(
        min_value=ZERO, max_digits=14, decimal_places=2,
        required=False, label="Stripe / processor fee"
    )
    fee_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), required=False,
        label="Processing fee expense account"
    )
    memo = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["revenue_account"].queryset = Account.objects.filter(
            is_active=True, account_type="income"
        ).exclude(number="4010", name="Sales Income").order_by("number")
        self.fields["deposit_account"].queryset = Account.objects.filter(
            is_active=True, account_type="asset"
        ).order_by("number")
        self.fields["authority"].queryset = tax_authorities()
        self.fields["fee_account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=("expense", "other_expense")
        ).order_by("number")
        if not self.is_bound:
            self.initial.setdefault("sale_date", timezone.localdate())
            self.initial.setdefault("taxable_amount", ZERO)
            self.initial.setdefault("processor_fee", ZERO)

    def clean(self):
        data = super().clean()
        source = data.get("source")
        amount = data.get("sale_amount")
        taxable = data.get("taxable_amount")
        tax = data.get("tax_collected")
        rate = data.get("tax_rate")
        fee = data.get("processor_fee") or ZERO
        when = data.get("sale_date")
        if when and when < LEDGER_START:
            self.add_error("sale_date", "The test ledger begins January 1, 2026.")
        if amount is not None and taxable is not None and taxable > amount:
            self.add_error("taxable_amount", "Taxable portion cannot exceed artwork price.")
        if source == "gallery":
            if taxable not in (None, ZERO):
                self.add_error("taxable_amount", "Gallery manages the tax. Enter zero taxable sales here.")
            if tax not in (None, ZERO):
                self.add_error("tax_collected", "Do not record tax remitted by the gallery as your liability.")
            if rate is not None:
                self.add_error("tax_rate", "Gallery tax is not calculated by this form.")
            if data.get("authority"):
                self.add_error("authority", "The gallery remits its own sales tax.")
            if fee:
                self.add_error("processor_fee", "Record gallery proceeds as received, with no processor fee here.")
            data["tax_collected"] = ZERO
        elif source == "cash":
            if tax is not None:
                self.add_error("tax_collected", "For cash sales, leave this empty; enter a looked-up tax rate.")
            if taxable is not None and taxable > ZERO and rate is None:
                self.add_error("tax_rate", "Enter the official combined tax rate for a taxable cash sale.")
            if rate is not None and taxable is not None:
                data["tax_collected"] = (taxable * rate / Decimal("100")).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
            else:
                data["tax_collected"] = ZERO
            if fee:
                self.add_error("processor_fee", "Cash sales cannot have a processor fee.")
        elif source == "stripe":
            if tax is None:
                self.add_error("tax_collected", "Enter the actual tax from Stripe, even when zero.")
            if rate is not None:
                self.add_error("tax_rate", "Use Stripe's actual tax amount instead of a rate.")
        if fee and not data.get("fee_account"):
            self.add_error("fee_account", "Choose an expense account for the processing fee.")
        if data.get("fee_account") and not fee:
            self.add_error("fee_account", "Enter the processing fee or clear its account.")
        if not self.errors:
            tax = data.get("tax_collected") or ZERO
            if tax > ZERO and not data.get("authority"):
                self.add_error("authority", "Choose Kansas or Missouri tax payable for tax you collected.")
            if taxable is not None and taxable > ZERO and not data.get("authority") and source != "gallery":
                self.add_error("authority", "Choose the applicable agency for taxable sales.")
            if amount is not None and amount + tax - fee <= ZERO:
                self.add_error("processor_fee", "The amount received must be positive.")
        return data


@transaction.atomic
def post_taxable_sale(data, *, actor=None):
    """Create one balanced posted sale, plus its linked tax reporting record."""
    revenue = Account.objects.select_for_update().get(pk=data["revenue_account"].pk)
    deposit = Account.objects.select_for_update().get(pk=data["deposit_account"].pk)
    authority = data.get("authority")
    fee_account = data.get("fee_account")
    price = data["sale_amount"]
    tax = data.get("tax_collected") or ZERO
    fee = data.get("processor_fee") or ZERO

    if not revenue.is_active or revenue.account_type != "income" or (
        revenue.number == "4010" and revenue.name == "Sales Income"
    ):
        raise ValidationError("Choose an active posting Income account, not the Sales Income subtotal.")
    if not deposit.is_active or deposit.account_type != "asset":
        raise ValidationError("Choose an active bank or cash asset.")
    if tax > ZERO and (
        authority is None or not authority.is_active or
        authority.number not in ("2007", "2010") or authority.account_type != "liability"
    ):
        raise ValidationError("Choose an active Kansas or Missouri tax payable account.")
    if fee > ZERO and (fee_account is None or not fee_account.is_active or fee_account.account_type not in ("expense", "other_expense")):
        raise ValidationError("Choose an active processing-fee expense account.")
    ensure_open_period(data["sale_date"])
    reference = (data.get("reference") or "").strip()
    if reference and JournalEntry.objects.filter(source="sales_tax_sale", source_reference=reference).exists():
        raise ValidationError("This sale reference is already recorded. Do not post it twice.")
    entry = JournalEntry.objects.create(
        date=data["sale_date"], payee="Customer",
        description=data["description"], memo=data.get("memo", ""),
        source="sales_tax_sale", source_reference=reference, created_by=actor,
    )
    JournalLine.objects.create(entry=entry, account=deposit, debit=price + tax - fee)
    if fee:
        JournalLine.objects.create(entry=entry, account=fee_account, debit=fee)
    JournalLine.objects.create(entry=entry, account=revenue, credit=price)
    if tax:
        JournalLine.objects.create(entry=entry, account=authority, credit=tax)
    entry = post_entry(entry.pk, actor=actor)
    record = SalesTaxRecord(
        sale_date=data["sale_date"], source=data["source"],
        jurisdiction=data.get("jurisdiction", ""),
        sale_amount=price, taxable_amount=data["taxable_amount"],
        tax_collected=tax, tax_rate=data.get("tax_rate"),
        authority=authority, journal_entry=entry, memo=data.get("memo", ""),
    )
    record.full_clean()
    record.save()
    return record


@staff_member_required(login_url="/admin/login/")
def sale_new(request):
    form = TaxableSaleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            post_taxable_sale(form.cleaned_data, actor=request.user)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, exc)
        else:
            return redirect("accounting:sales_tax")
    return render(request, "accounting/sales_tax_sale_form.html", {"form": form})
