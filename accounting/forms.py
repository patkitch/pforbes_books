# accounting/forms.py
from decimal import Decimal
from django import forms
from django.core.validators import MinValueValidator

from django_ledger.models import InvoiceModel, CustomerModel ,BillModel, VendorModel

class ApplyPaymentForm(forms.Form):
    bill = forms.ModelChoiceField(queryset=BillModel.objects.all())
    vendor = forms.ModelChoiceField(queryset=VendorModel.objects.all())
    invoice = forms.ModelChoiceField(queryset=InvoiceModel.objects.all())
    customer = forms.ModelChoiceField(queryset=CustomerModel.objects.all())
    payment_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    payment_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    discount_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, initial=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    method = forms.ChoiceField(choices=[("cash","Cash"),("check","Check"),("card","Card"),("ach","ACH")])
    reference = forms.CharField(required=False, help_text="Check #, last 4, etc.")

    def clean(self):
        data = super().clean()
        bill = data.get("bill")
        vendor = data.get("vendor")
        invoice = data.get("invoice")
        customer = data.get("customer")
        pay = data.get("payment_amount") or Decimal("0.00")
        disc = data.get("discount_amount") or Decimal("0.00")

        # If your InvoiceModel has a FK named "customer", this check will work.
        # If it's named differently, adjust the attribute below.
        if bill and vendor and getattr(bill, "vendor_id", None) != getattr(vendor, "id", None):
            raise forms.ValidationError("Selected bill does not belong to that vendor.")

        if invoice and customer and getattr(invoice, "customer_id", None) != getattr(customer, "id", None):
            raise forms.ValidationError("Selected invoice does not belong to that customer.")

        # If you track remaining balance on InvoiceModel, you can validate amounts here.
        # Otherwise, leave only non-negative checks.
        if pay < 0 or disc < 0:
            raise forms.ValidationError("Amounts cannot be negative.")

        return data

