"""Django intake form for Vincent's original artwork workflow.

This module only defines and validates form inputs. It does not create products,
upload images, or modify WooCommerce. Import as web_automation.vincent_forms
when installed in that app.
"""

from decimal import Decimal

from django import forms


CANVAS_PROFILE_CHOICES = [
    ("traditional", "Traditional / Slim (0.5–0.75 in)"),
    ("gallery", "Gallery / Deep Edge (1.25–1.5 in)"),
    ("museum", "Museum / Ultra-Deep (2–2.5 in)"),
    ("flat", "Flat Panel / Board (0.125–0.25 in)"),
]

SHIPPING_SIZE_CHOICES = [
    ("sm", "Small (SM)"),
    ("m", "Medium (M)"),
    ("l", "Large (L)"),
    ("xl", "Extra Large (XL)"),
]


class VincentOriginalArtworkForm(forms.Form):
    """Collect original-artwork details for later preview and draft creation."""

    title = forms.CharField(
        label="Artwork Title", max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Storm Gathering Across the Prairie"}),
    )
    style = forms.CharField(
        label="Art Style", max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Abstract Impressionism"}),
    )
    medium = forms.CharField(
        label="Medium", max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Acrylic on canvas"}),
    )
    width = forms.DecimalField(
        label="Artwork Width (inches)", min_value=Decimal("0.01"),
        max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    height = forms.DecimalField(
        label="Artwork Height (inches)", min_value=Decimal("0.01"),
        max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    canvas_profile = forms.ChoiceField(
        label="Canvas Type / Profile", choices=CANVAS_PROFILE_CHOICES,
        widget=forms.Select,
    )
    framed = forms.TypedChoiceField(
        label="Is the artwork framed?",
        choices=[("false", "Unframed"), ("true", "Framed")],
        coerce=lambda x: x == "true", empty_value=False,
        widget=forms.RadioSelect, initial="false",
    )
    frame_width = forms.DecimalField(
        label="Outside Frame Width (inches)", required=False,
        min_value=Decimal("0.01"), max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    frame_height = forms.DecimalField(
        label="Outside Frame Height (inches)", required=False,
        min_value=Decimal("0.01"), max_digits=7, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    shipping_size = forms.ChoiceField(
        label="Shipping Size (select manually)", choices=SHIPPING_SIZE_CHOICES,
        widget=forms.Select,
    )
    price = forms.DecimalField(
        label="Original Artwork Price (USD)", min_value=Decimal("0.01"),
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    subject = forms.CharField(
        label="Subject (optional)", max_length=200, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Ocean, mountains, Kansas prairie"}),
    )
    story_notes = forms.CharField(
        label="Artist's Story / Why I Created This Painting (optional)", required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
    )
    image_url = forms.URLField(
        label="Main WordPress Image URL (optional for now)", required=False,
        widget=forms.URLInput(attrs={"placeholder": "https://pforbesart.com/wp-content/uploads/..."}),
        help_text="Image upload/attachment will be integrated later. No upload happens in this form.",
    )

    def clean(self):
        data = super().clean()
        if data.get("framed") is True:
            for key in ("frame_width", "frame_height"):
                if data.get(key) is None and key not in self.errors:
                    self.add_error(key, "Required when the artwork is framed.")
        else:
            # A previously entered frame measurement must not be applied to
            # an unframed painting after the radio button is changed.
            data["frame_width"] = None
            data["frame_height"] = None
        return data
