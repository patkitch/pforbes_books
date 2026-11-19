"""Owner-funded transactions. Manual draft/post workflow; no bank import involved."""
from datetime import date
from decimal import Decimal

from django import forms

from .models import Account
from .period_controls import period_is_locked, LEDGER_START


class OwnerContributionForm(forms.Form):
    KIND_CHOICES = [
        ("cash", "Money contributed to the business bank account"),
        ("personal_expense", "Business expense paid with personal funds"),
    ]
    kind = forms.ChoiceField(choices=KIND_CHOICES, label="Contribution type")
    date = forms.DateField(initial=LEDGER_START, widget=forms.DateInput(attrs={"type": "date"}))
    payee = forms.CharField(max_length=200, required=False, label="Payee / source")
    description = forms.CharField(max_length=255)
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2)
    contribution_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="Owner contribution (equity) account")
    destination_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Bank account or expense category"
    )
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    save_action = forms.ChoiceField(
        choices=(("draft", "Save draft"), ("post", "Post transaction")),
        widget=forms.RadioSelect, initial="draft",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contribution_account"].queryset = Account.objects.filter(
            is_active=True, account_type="equity"
        ).order_by("number")
        # Queryset permits both; clean() enforces type based on contribution kind.
        self.fields["destination_account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=("asset", "cogs", "expense", "other_expense")
        ).order_by("number")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date") and period_is_locked(cleaned["date"]):
            self.add_error("date", "This accounting period is locked.")
        kind = cleaned.get("kind")
        equity = cleaned.get("contribution_account")
        destination = cleaned.get("destination_account")
        if equity and equity.account_type != "equity":
            self.add_error("contribution_account", "Choose an owner contribution equity account.")
        if destination:
            allowed = {"asset"} if kind == "cash" else {"cogs", "expense", "other_expense"}
            if destination.account_type not in allowed:
                self.add_error(
                    "destination_account",
                    "Choose a bank account for cash contributions, or an expense category for personally paid expenses.",
                )
        if cleaned.get("date") and cleaned["date"] < LEDGER_START:
            self.add_error("date", "This new ledger begins January 1, 2026.")
        if equity and destination and equity.pk == destination.pk:
            self.add_error("destination_account", "Choose two different accounts.")
        return cleaned
