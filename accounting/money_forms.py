"""Manual money movements and refunds. All choices produce balanced journal entries.

Bank transfers, card payments, owner draws, and purchase/sales refunds are not
ordinary income or expenses. This form validates the particular accounts for
each workflow before the journal is saved.
"""
from datetime import date
from decimal import Decimal

from django import forms

from .models import Account


MOVEMENT_TYPES = (
    ("transfer", "Transfer between business bank/cash accounts"),
    ("card_payment", "Pay a business credit card from a business bank account"),
    ("owner_draw", "Owner withdrawal / distribution"),
    ("owner_card_payment", "Pay a business credit card with personal funds"),
    ("purchase_refund", "Refund received for a business purchase"),
    ("sales_refund", "Refund paid to a customer"),
)


def valid_account_types(kind):
    """Debit account types, credit account types, and explanatory labels."""
    mapping = {
        "transfer": ({"asset"}, {"asset"}),
        "card_payment": ({"liability"}, {"asset"}),
        "owner_draw": ({"equity"}, {"asset"}),
        "owner_card_payment": ({"liability"}, {"equity"}),
        "purchase_refund": ({"asset", "liability"}, {"cogs", "expense", "other_expense"}),
        "sales_refund": ({"income", "other_income"}, {"asset", "liability"}),
    }
    return mapping.get(kind, (set(), set()))


class MoneyMovementForm(forms.Form):
    kind = forms.ChoiceField(choices=MOVEMENT_TYPES, label="Transaction type")
    date = forms.DateField(
        initial=date(2027, 1, 1),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    payee = forms.CharField(max_length=200, required=False, label="Payee / institution")
    description = forms.CharField(max_length=255)
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2)
    debit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Receiving / debit account"
    )
    credit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Paying / credit account"
    )
    memo = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    save_action = forms.ChoiceField(
        choices=(("draft", "Save draft"), ("post", "Post transaction")),
        widget=forms.RadioSelect, initial="draft",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        eligible = Account.objects.filter(is_active=True).order_by("number")
        self.fields["debit_account"].queryset = eligible
        self.fields["credit_account"].queryset = eligible

    def clean(self):
        result = super().clean()
        kind = result.get("kind")
        debit = result.get("debit_account")
        credit = result.get("credit_account")
        debit_types, credit_types = valid_account_types(kind)
        if debit and debit.account_type not in debit_types:
            self.add_error("debit_account", "Receiving/debit account is not valid for this transaction type.")
        if credit and credit.account_type not in credit_types:
            self.add_error("credit_account", "Paying/credit account is not valid for this transaction type.")
        if debit and credit and debit.pk == credit.pk:
            self.add_error("credit_account", "Use two different accounts.")
        if result.get("date") and result["date"] < date(2027, 1, 1):
            self.add_error("date", "This new ledger begins January 1, 2027.")
        return result
