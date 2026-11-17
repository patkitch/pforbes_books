"""First manual entry workflow: straightforward income and expense transactions."""
from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Account
from accounting_contacts.models import Customer, Vendor
from .period_controls import period_is_locked


class SimpleTransactionForm(forms.Form):
    KIND_CHOICES = (("expense", "Expense / purchase"), ("income", "Income / receipt"))
    kind = forms.ChoiceField(choices=KIND_CHOICES)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=date(2027, 1, 1))
    payee = forms.CharField(max_length=200, required=False, label="Payee / customer")
    description = forms.CharField(max_length=255, label="Description")
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2)
    category_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="Income / expense category")
    payment_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="Bank / credit card account")
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none(), required=False, label="Vendor (optional)")
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label="Customer (optional)")
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    save_action = forms.ChoiceField(choices=(("draft", "Save draft"), ("post", "Post transaction")), widget=forms.RadioSelect, initial="draft")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kind = (self.data.get("kind") if self.is_bound else self.initial.get("kind", "expense"))
        self.fields["category_account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=["expense", "cogs", "income", "other_income", "other_expense"]
        ).order_by("number")
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["payment_account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=["asset", "liability"]
        ).order_by("number")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date") and period_is_locked(cleaned["date"]):
            self.add_error("date", "This accounting period is locked.")
        kind = cleaned.get("kind")
        if cleaned.get("vendor") and cleaned.get("customer"):
            self.add_error("customer", "Choose a vendor or customer, not both.")
        if cleaned.get("vendor") and kind != "expense":
            self.add_error("vendor", "Choose a vendor for purchases.")
        if cleaned.get("customer") and kind != "income":
            self.add_error("customer", "Choose a customer for sales.")
        category = cleaned.get("category_account")
        payment = cleaned.get("payment_account")
        if category:
            allowed = {"expense", "cogs", "other_expense"} if kind == "expense" else {"income", "other_income"}
            if category.account_type not in allowed:
                self.add_error("category_account", "Choose a category that matches the transaction type.")
        if payment and payment.account_type not in ("asset", "liability"):
            self.add_error("payment_account", "Choose an active bank, cash, or credit card account.")
        if cleaned.get("date") and cleaned["date"].year < 2027:
            self.add_error("date", "This new ledger begins January 1, 2027.")
        return cleaned
