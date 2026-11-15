from django import forms
from django.core.exceptions import ValidationError

from .models import Account


PREFIX_BY_TYPE = {
    "asset": "1", "liability": "2", "equity": "3", "income": "4",
    "cogs": "5", "expense": "6", "other_income": "7", "other_expense": "8",
}


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["number", "name", "account_type", "detail_type", "parent", "memo"]
        widgets = {
            "number": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": "4"}),
            "memo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
