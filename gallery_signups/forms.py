from django import forms

from .models import FeaturedArtistEvent


class MemberPasswordForm(forms.Form):
    password = forms.CharField(label="Gallery member password", widget=forms.PasswordInput, max_length=128)


class ClaimSlotForm(forms.Form):
    name = forms.CharField(label="Your name", max_length=120)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter your name.")
        return name


class AdminLoginForm(forms.Form):
    username = forms.CharField(max_length=80)
    password = forms.CharField(widget=forms.PasswordInput, max_length=128)


class SlotEditForm(forms.Form):
    artist_name = forms.CharField(required=False, max_length=120, label="Name")
    reservation_label = forms.CharField(required=False, max_length=120)


class EventEditForm(forms.Form):
    title = forms.CharField(required=False, max_length=120)
    is_closed = forms.BooleanField(required=False)


class MemberSettingsForm(forms.Form):
    member_password = forms.CharField(label="New shared member password", widget=forms.PasswordInput, min_length=8, max_length=128)


class AdministratorForm(forms.Form):
    username = forms.CharField(max_length=80)
    password = forms.CharField(widget=forms.PasswordInput, min_length=12, max_length=128)


class MultiImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiImageField(forms.FileField):
    widget = MultiImageInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        image_field = forms.ImageField()
        cleaned = []
        for uploaded in files:
            image_field.clean(uploaded)
            if uploaded.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Each image must be 5 MB or smaller.")
            cleaned.append(uploaded)
        return cleaned


class GalleryArtistApplicationForm(forms.Form):
    artist_name = forms.CharField(label="Artist name", max_length=160)
    address = forms.CharField(label="Mailing address", widget=forms.Textarea(attrs={"rows": 3}), max_length=500)
    email = forms.EmailField(label="Email")
    phone = forms.CharField(label="Phone", max_length=40)
    medium = forms.CharField(label="Primary medium", max_length=120)
    artwork_url = forms.URLField(label="Link to your artwork", required=False)
    wall_count = forms.ChoiceField(
        label="Number of walls requested",
        choices=[("1", "One wall — $100"), ("2", "Two walls — $200")],
    )
    preferred_months = forms.ModelMultipleChoiceField(
        label="Months you would like to be considered for",
        queryset=FeaturedArtistEvent.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select one or more available months, in order of preference if possible.",
    )
    images = MultiImageField(
        label="Or upload up to five artwork images",
        required=False,
        help_text="Accepted: image files up to 5 MB each.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preferred_months"].queryset = FeaturedArtistEvent.objects.filter(year=2027).order_by("event_date")

    def clean_artist_name(self):
        name = self.cleaned_data["artist_name"].strip()
        if not name:
            raise forms.ValidationError("Enter your name.")
        return name

    def clean_medium(self):
        return self.cleaned_data["medium"].strip()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("artwork_url") and not cleaned.get("images"):
            raise forms.ValidationError("Please provide an artwork link or upload at least one image.")
        if len(cleaned.get("images") or []) > 5:
            self.add_error("images", "You may upload no more than five images.")
        return cleaned


class ApplicationDecisionForm(forms.Form):
    selected_event = forms.ModelChoiceField(
        queryset=FeaturedArtistEvent.objects.none(),
        label="Approved month",
    )
    admin_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, application=None, **kwargs):
        super().__init__(*args, **kwargs)
        events = FeaturedArtistEvent.objects.filter(year=2027).order_by("event_date")
        if application:
            preferred_ids = application.preferred_months
            events = events.filter(pk__in=preferred_ids)
        self.fields["selected_event"].queryset = events
