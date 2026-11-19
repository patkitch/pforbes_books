from django import forms
from django.core.exceptions import ValidationError

from .models import Account


PREFIX_BY_TYPE = {
    "asset": "1", "liability": "2", "equity": "3", "income": "4",
    "cogs": "5", "expense": "6", "other_income": "7", "other_expense": "8",
}


class AccountForm(forms.ModelForm):
    account_type = forms.ChoiceField(
        choices=[("", "Choose account type")] + [
            (key, f"{label} — {Account.DEFAULT_BALANCES[key].title()}")
            for key, label in Account.TYPES
        ],
        label="Account Type (usual balance)",
    )
    normal_balance = forms.ChoiceField(
        choices=[("debit", "Debit"), ("credit", "Credit")],
        label="Normal Balance",
        required=False,
        help_text="Choose which side ordinarily increases this account. "
                  "Contra accounts can use the opposite side; both debit and credit entries remain allowed.",
    )
    class Meta:
        model = Account
        fields = ["number", "name", "account_type", "normal_balance", "detail_type", "parent", "memo"]
        widgets = {
            "number": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": "4"}),
            "memo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["normal_balance"].initial = (
                self.instance.normal_side if self.instance.pk else "debit"
            )
        parents = Account.objects.filter(is_active=True)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
            if self.instance.parent_id:
                parents = Account.objects.filter(pk=self.instance.parent_id) | parents
        self.fields["parent"].queryset = parents.distinct().order_by("number")
        self.fields["parent"].required = False

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("number")
        kind = cleaned.get("account_type")
        if kind and not cleaned.get("normal_balance"):
            cleaned["normal_balance"] = Account.DEFAULT_BALANCES[kind]
        parent = cleaned.get("parent")
        if number and kind and not number.startswith(PREFIX_BY_TYPE[kind]):
            self.add_error("number", "Account number does not match its account type range.")
        if parent and kind and parent.account_type != kind:
            self.add_error("parent", "Parent account must be the same account type.")
        if self.instance.pk and Account.objects.filter(parent=self.instance).exists():
            if kind != self.instance.account_type:
                self.add_error("account_type", "Cannot change account type while subaccounts exist.")
        if self.instance.pk and self.instance.journal_lines.exists():
            if kind != self.instance.account_type:
                self.add_error("account_type", "Cannot change account type after transactions exist.")
            if parent != self.instance.parent:
                self.add_error("parent", "Cannot move an account with transactions to a different parent.")
        return cleaned
