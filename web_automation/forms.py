from django import forms


class NewProductForm(forms.Form):
    title = forms.CharField(
        label="Artwork Title",
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Breaking Into Dusk"}),
    )

    medium = forms.CharField(
        label="Medium",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Acrylic on canvas"}),
    )

    subject = forms.CharField(
        label="Subject / Theme",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Kansas prairie, lighthouse, ocean, dog"}),
    )

    story_notes = forms.CharField(
        label="Story / Story Notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "What’s the story behind this piece? Why did you paint it? Any emotion or memory?"
            }
        ),
    )

    image_url = forms.URLField(
        label="WordPress Image URL (optional)",
        required=False,
        widget=forms.URLInput(
            attrs={"placeholder": "https://pforbesart.com/wp-content/uploads/..."}
        ),
    )

    media_id = forms.CharField(
        label="WordPress Media ID (optional)",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. 5389"}),
    )

    notes_for_agent = forms.CharField(
        label="Notes for Automation Agent (optional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Any instructions: pricing hints, collection info, gallery notes, etc."
            }
        ),
    )



class ProductChoiceForm(forms.Form):
    title_choice = forms.ChoiceField(
        label="Choose a title",
        widget=forms.RadioSelect,
    )
    custom_title = forms.CharField(
        label="Or write your own title",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Custom title (optional)"}),
    )

    short_desc_choice = forms.ChoiceField(
        label="Choose a short description",
        widget=forms.RadioSelect,
    )
    custom_short_desc = forms.CharField(
        label="Or write your own short description",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Custom short description (optional)",
            }
        ),
    )

    long_desc_choice = forms.ChoiceField(
        label="Choose a long description",
        widget=forms.RadioSelect,
    )
    custom_long_desc = forms.CharField(
        label="Or write your own long description",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Custom long description (optional)",
            }
        ),
    )

    alt_text_choice = forms.ChoiceField(
        label="Choose alt text",
        widget=forms.RadioSelect,
    )
    custom_alt_text = forms.CharField(
        label="Or write your own alt text",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Custom alt text (optional)",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        suggestions = kwargs.pop("suggestions", None) or {}
        super().__init__(*args, **kwargs)

        def make_choices(key):
            items = suggestions.get(key, [])
            return [(str(i), items[i]) for i in range(len(items))]

        self.fields["title_choice"].choices = make_choices("titles")
        self.fields["short_desc_choice"].choices = make_choices("short_descriptions")
        self.fields["long_desc_choice"].choices = make_choices("long_descriptions")
        self.fields["alt_text_choice"].choices = make_choices("alt_texts")

        # Default to first option for each if available
        if self.fields["title_choice"].choices:
            self.fields["title_choice"].initial = self.fields["title_choice"].choices[0][0]
        if self.fields["short_desc_choice"].choices:
            self.fields["short_desc_choice"].initial = self.fields["short_desc_choice"].choices[0][0]
        if self.fields["long_desc_choice"].choices:
            self.fields["long_desc_choice"].initial = self.fields["long_desc_choice"].choices[0][0]
        if self.fields["alt_text_choice"].choices:
            self.fields["alt_text_choice"].initial = self.fields["alt_text_choice"].choices[0][0]

class SEOProductLookupForm(forms.Form):
    product_id = forms.IntegerField(
        label="WooCommerce Product ID",
        min_value=1,
        help_text="Enter the product ID from WooCommerce to see SEO suggestions.",
    )