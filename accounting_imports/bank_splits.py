"""Purchase allocation validation; no journal posting."""
from decimal import Decimal
from django import forms
from accounting.models import Account

EXPENSE_TYPES = ("expense", "cogs", "other_expense")
MAX_SPLITS = 12


class SplitLineForm(forms.Form):
    kind = forms.ChoiceField(choices=[("", "Choose type"), ("business", "Business"), ("personal", "Personal")], required=False)
    category = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    memo = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Account.objects.filter(is_active=True, account_type__in=EXPENSE_TYPES)

    def clean(self):
        data = super().clean()
        if not any(data.values()):
            return data
        kind, category, amount = data.get("kind"), data.get("category"), data.get("amount")
        if not kind:
            self.add_error("kind", "Choose business or personal.")
        if amount is None:
            self.add_error("amount", "Enter a positive amount.")
        if kind == "business" and not category:
            self.add_error("category", "Choose a business expense category.")
        if kind == "personal" and category:
            self.add_error("category", "Personal portions cannot have a business category.")
        return data


SplitFormSet = forms.formset_factory(SplitLineForm, extra=2, max_num=MAX_SPLITS,
                                     validate_max=True, absolute_max=MAX_SPLITS)


def validate_allocations(formset, amount):
    if not formset.is_valid():
        return None, "Correct the allocation lines."
    lines = []
    for data in formset.cleaned_data:
        if not data or not data.get("kind"):
            continue
        lines.append({"kind": data["kind"], "category": data["category"].pk if data.get("category") else None,
                      "amount": str(data["amount"].quantize(Decimal("0.01"))), "memo": data.get("memo", "")})
    if len(lines) < 2:
        return None, "Enter at least two allocation lines."
    total = sum((Decimal(line["amount"]) for line in lines), Decimal("0"))
    business = sum((Decimal(line["amount"]) for line in lines if line["kind"] == "business"), Decimal("0"))
    if total != abs(amount):
        return None, "The allocation total must exactly equal the original purchase amount."
    if not business:
        return None, "Use Personal — exclude for an entirely personal purchase."
    return lines, ""
