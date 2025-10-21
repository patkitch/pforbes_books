# books/forms.py
from django import forms
from django_ledger.models import AccountModel, BillModel
from .models import BillExtras


class BillExtrasForm(forms.ModelForm):
    class Meta:
        model = BillExtras
        fields = [
            "default_expense_acct",
            "cash_account_override",
            "discount_method",
            "discount_value",
            "discount_account",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bill: BillModel | None = getattr(self.instance, "bill", None)
        # If editing via Inline, self.instance.bill is set; otherwise check initial
        if not bill and "bill" in self.initial:
            bill = self.initial["bill"]
        if bill and getattr(bill, "entity_id", None):
            qs = AccountModel.objects.filter(entity_id=bill.entity_id)
            self.fields["default_expense_acct"].queryset = qs
            self.fields["cash_account_override"].queryset = qs
            self.fields["discount_account"].queryset = qs


