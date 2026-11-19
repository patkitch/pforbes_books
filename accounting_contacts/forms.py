"""Contact and receipt editing forms. Accounting entries remain separate."""
from pathlib import Path

from django import forms

from .models import Customer, Receipt, ReceiptItem, TransactionParty, Vendor

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_RECEIPT_BYTES = 10 * 1024 * 1024


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = (
            "name", "email", "phone", "website", "address1", "address2",
            "city", "state", "postal_code", "country", "default_account_number",
            "notes", "is_active",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            "name", "kind", "email", "phone", "billing_address1",
            "billing_address2", "billing_city", "billing_state", "billing_postal_code",
            "billing_country", "shipping_address1", "shipping_address2",
            "shipping_city", "shipping_state", "shipping_postal_code",
            "shipping_country", "notes", "is_active",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class ArtworkItemForm(forms.Form):
    artwork_title = forms.CharField(max_length=200, required=False, label="Artwork title")
    item_type = forms.ChoiceField(
        choices=(("", "Select type"), *ReceiptItem.ITEM_TYPES),
        required=False, label="Original or print",
    )
    size = forms.CharField(max_length=80, required=False, label="Artwork / print size")
    quantity = forms.IntegerField(min_value=1, required=False, label="Quantity")
    unit_price = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0,
        required=False, label="Unit price",
    )

    def clean(self):
        data = super().clean()
        if any(data.get(key) not in (None, "") for key in
               ("artwork_title", "item_type", "size", "quantity", "unit_price")):
            for key in ("artwork_title", "item_type", "quantity", "unit_price"):
                if data.get(key) in (None, ""):
                    self.add_error(key, "Complete this field for an artwork item.")
        return data


ArtworkItemFormSet = forms.formset_factory(
    ArtworkItemForm, extra=3, max_num=12, validate_max=True
)


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = (
            "title", "receipt_type", "date", "amount",
            "vendor", "customer", "journal_entry_id", "attachment", "notes",
        )
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"journal_entry_id": "Accounting transaction ID (optional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["journal_entry_id"].required = False

    def clean_attachment(self):
        upload = self.cleaned_data.get("attachment")
        if not upload:
            return upload
        # Existing file on edited record has no incoming bytes to validate.
        if not hasattr(upload, "read"):
            return upload
        extension = Path(upload.name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Attach a PDF, JPG, PNG, or WebP file.")
        if upload.size > MAX_RECEIPT_BYTES:
            raise forms.ValidationError("Receipt file must be 10 MB or smaller.")
        header = upload.read(16)
        upload.seek(0)
        signature_ok = (
            (extension == ".pdf" and header.startswith(b"%PDF-"))
            or (extension in (".jpg", ".jpeg") and header.startswith(b"\xff\xd8\xff"))
            or (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
            or (extension == ".webp" and header.startswith(b"RIFF") and header[8:12] == b"WEBP")
        )
        if not signature_ok:
            raise forms.ValidationError("The uploaded file contents do not match its document type.")
        return upload

    def clean(self):
        cleaned = super().clean()
        vendor, customer = cleaned.get("vendor"), cleaned.get("customer")
        kind = cleaned.get("receipt_type")
        if vendor and customer:
            self.add_error("customer", "Choose a vendor or customer, not both.")
        if kind == "purchase" and customer:
            self.add_error("customer", "Purchase receipt should be linked to a vendor.")
        if kind == "sale" and vendor:
            self.add_error("vendor", "Sales receipt should be linked to a customer.")
        # Protect manually entered receipts from accidental duplicate saves.
        # Imported receipts have an independent source/reference uniqueness rule.
        title = cleaned.get("title")
        recorded_date = cleaned.get("date")
        amount = cleaned.get("amount")
        if title and recorded_date and amount is not None and kind and self.instance.source == "manual":
            duplicate = Receipt.objects.filter(
                title__iexact=title.strip(), receipt_type=kind,
                date=recorded_date, amount=amount,
                vendor=vendor, customer=customer, source="manual",
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error(
                    "title",
                    "An identical manual receipt already exists for this contact, date and amount. "
                    "Open the existing receipt instead of saving another copy.",
                )
        return cleaned


class TransactionPartyForm(forms.Form):
    party_type = forms.ChoiceField(
        choices=(("vendor", "Vendor"), ("customer", "Customer")),
        label="Contact type",
    )
    vendor = forms.ModelChoiceField(
        queryset=Vendor.objects.none(), required=False,
        label="Vendor",
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(), required=False,
        label="Customer",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)

    def clean(self):
        data = super().clean()
        kind = data.get("party_type")
        if kind == "vendor" and not data.get("vendor"):
            self.add_error("vendor", "Choose a vendor, or create a vendor first.")
        if kind == "customer" and not data.get("customer"):
            self.add_error("customer", "Choose a customer, or create a customer first.")
        return data
