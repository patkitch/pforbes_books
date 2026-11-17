"""Fixed five-line split form for basic income and expense transactions.

Only the categories that have BOTH an account and an amount are used.
A split must use at least two categories; the opposite side is one bank/card account.
"""
from datetime import date
from decimal import Decimal

from django import forms

from .models import Account
from accounting_contacts.models import Customer, Vendor
from .period_controls import period_is_locked


class SplitTransactionForm(forms.Form):
    kind = forms.ChoiceField(choices=(("expense", "Expense / purchase"), ("income", "Income / receipt")))
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), initial=date(2027, 1, 1))
    payee = forms.CharField(max_length=200, required=False, label="Payee / customer")
    description = forms.CharField(max_length=255)
    payment_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="Bank / credit card account")
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none(), required=False, label="Vendor (optional)")
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label="Customer (optional)")
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    save_action = forms.ChoiceField(
        choices=(("draft", "Save draft"), ("post", "Post transaction")),
        widget=forms.RadioSelect, initial="draft",
    )
    MAX_SPLITS = 5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["payment_account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=["asset", "liability"]
        ).order_by("number")
        options = Account.objects.filter(
            is_active=True,
            account_type__in=["expense", "cogs", "other_expense", "income", "other_income"],
        ).order_by("number")
        self.split_fields = []
        for n in range(1, self.MAX_SPLITS + 1):
            category_name = f"category_{n}"
            amount_name = f"amount_{n}"
            self.fields[category_name] = forms.ModelChoiceField(
                queryset=options, required=False, label=f"Category {n}"
            )
            self.fields[amount_name] = forms.DecimalField(
                min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
                required=False, label=f"Amount {n}"
            )
            self.split_fields.append((self[category_name], self[amount_name]))

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
        if kind not in ("expense", "income"):
            return cleaned
        if cleaned.get("date") and cleaned["date"].year < 2027:
            self.add_error("date", "This ledger begins January 1, 2027.")
        acceptable = (
            {"expense", "cogs", "other_expense"} if kind == "expense"
            else {"income", "other_income"}
        )
        lines = []
        for n in range(1, self.MAX_SPLITS + 1):
            account = cleaned.get(f"category_{n}")
            amount = cleaned.get(f"amount_{n}")
            if (account is None) != (amount is None):
                self.add_error(
                    f"category_{n}" if account is None else f"amount_{n}",
                    "Enter both the account and amount for this split.",
                )
            elif account is not None and amount is not None:
                if account.account_type not in acceptable:
                    self.add_error(f"category_{n}", "Category does not match transaction kind.")
                lines.append((account, amount))
        if len(lines) < 2:
            raise forms.ValidationError("Enter at least two complete split categories.")
        if not self.errors:
            cleaned["split_lines"] = lines
            cleaned["split_total"] = sum((amount for _, amount in lines), Decimal("0.00"))
        return cleaned
