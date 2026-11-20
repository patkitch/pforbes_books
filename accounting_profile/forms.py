from django import forms
from .models import BusinessProfile


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = [
            "display_name", "legal_name", "entity_type", "industry",
            "address_line_1", "address_line_2", "city", "state",
            "postal_code", "country", "contact_email", "contact_phone",
            "website", "tax_id_type", "tax_id_last_four", "notes",
        ]
        labels = {
            "display_name": "Business name",
            "legal_name": "Legal business name",
            "entity_type": "Business type",
            "tax_id_type": "Tax identification method",
            "tax_id_last_four": "Tax ID — last four digits only (optional)",
            "notes": "Business notes / related services",
        }
        help_texts = {
            "tax_id_last_four": "Do not enter a complete EIN or Social Security number. This is not a secure tax-ID vault or a Plaid application.",
            "notes": "Describe any related service or booking app; this does not connect or merge another company's books.",
        }

    def clean_tax_id_last_four(self):
        value = self.cleaned_data.get("tax_id_last_four", "").strip()
        if value and (len(value) != 4 or not value.isascii() or not value.isdigit()):
            raise forms.ValidationError("Enter exactly the last four digits, never a complete tax ID.")
        return value
