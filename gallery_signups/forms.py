from django import forms

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
