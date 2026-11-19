"""Advanced manual journal entry for cases not covered by guided forms."""
from datetime import date
from decimal import Decimal

from django import forms

from .models import Account
from .period_controls import period_is_locked, LEDGER_START


class GeneralJournalForm(forms.Form):
    MAX_LINES = 8
    date = forms.DateField(initial=LEDGER_START, widget=forms.DateInput(attrs={"type": "date"}))
    payee = forms.CharField(max_length=200, required=False)
    description = forms.CharField(max_length=255)
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    save_action = forms.ChoiceField(
        choices=(("draft", "Save draft"), ("post", "Post transaction")),
        widget=forms.RadioSelect, initial="draft",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = Account.objects.filter(is_active=True).order_by("number")
        self.journal_fields = []
        for n in range(1, self.MAX_LINES + 1):
            self.fields[f"account_{n}"] = forms.ModelChoiceField(
                queryset=options, required=False, label=f"Account {n}"
            )
            self.fields[f"debit_{n}"] = forms.DecimalField(
                min_value=Decimal("0.00"), max_digits=14, decimal_places=2,
                required=False, label=f"Debit {n}",
            )
            self.fields[f"credit_{n}"] = forms.DecimalField(
                min_value=Decimal("0.00"), max_digits=14, decimal_places=2,
                required=False, label=f"Credit {n}",
            )
            self.journal_fields.append((
                self[f"account_{n}"], self[f"debit_{n}"], self[f"credit_{n}"]
            ))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date") and period_is_locked(cleaned["date"]):
            self.add_error("date", "This accounting period is locked.")
        if cleaned.get("date") and cleaned["date"] < LEDGER_START:
            self.add_error("date", "This ledger begins January 1, 2026.")
        lines = []
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        for n in range(1, self.MAX_LINES + 1):
            account = cleaned.get(f"account_{n}")
            debit = cleaned.get(f"debit_{n}") or Decimal("0.00")
            credit = cleaned.get(f"credit_{n}") or Decimal("0.00")
            any_amount = debit != 0 or credit != 0
            if account is None and not any_amount:
                continue
            if account is None:
                self.add_error(f"account_{n}", "Select an account for this line.")
                continue
            if (debit > 0) == (credit > 0):
                self.add_error(f"debit_{n}", "Enter a positive debit OR credit, not both.")
                continue
            lines.append((account, debit, credit))
            total_debit += debit
            total_credit += credit
        if len(lines) < 2:
            raise forms.ValidationError("Enter at least two complete journal lines.")
        if total_debit <= 0 or total_debit != total_credit:
            raise forms.ValidationError("Journal debits and credits must balance exactly.")
        if not self.errors:
            cleaned["journal_lines"] = lines
        return cleaned
