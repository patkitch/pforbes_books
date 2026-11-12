from django import forms
from django.utils import timezone
from .models import Artwork,InventoryActivity,Location,Original,PrintOption
from .services import record_activity

class ArtworkForm(forms.ModelForm):
    initial_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False)
    price=forms.DecimalField(max_digits=10,decimal_places=2,min_value=0,required=False)
    canvas_profile=forms.CharField(max_length=80,required=False)
    framed=forms.BooleanField(required=False)
    outside_width_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    outside_height_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    class Meta:
        model=Artwork
        fields=["title","story","style","medium","width_inches","height_inches","support","image_url"]
        widgets={"story":forms.Textarea(attrs={"rows":4})}
    def save(self,commit=True):
        art=super().save(commit=commit)
        if commit: Original.objects.create(artwork=art,location=self.cleaned_data.get("initial_location"),price=self.cleaned_data.get("price"),canvas_profile=self.cleaned_data.get("canvas_profile",""),framed=self.cleaned_data.get("framed",False),outside_width_inches=self.cleaned_data.get("outside_width_inches"),outside_height_inches=self.cleaned_data.get("outside_height_inches"))
        return art

class PrintOptionForm(forms.ModelForm):
    class Meta:
        model=PrintOption
        fields=["artwork","label","width_inches","height_inches","format","finish_details","price","is_active","listing_status","woo_product_id","woo_url"]

class ActivityForm(forms.Form):
    item_type=forms.ChoiceField(choices=[("original","Original"),("print","Print option")])
    original=forms.ModelChoiceField(queryset=Original.objects.select_related("artwork"),required=False)
    print_option=forms.ModelChoiceField(queryset=PrintOption.objects.select_related("artwork").filter(is_active=True),required=False)
    kind=forms.ChoiceField(choices=InventoryActivity.KINDS)
    quantity=forms.IntegerField(min_value=1,initial=1)
    activity_date=forms.DateField(initial=timezone.localdate,widget=forms.DateInput(attrs={"type":"date"}))
    from_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False)
    to_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False)
    source=forms.CharField(max_length=100,required=False)
    reference=forms.CharField(max_length=100,required=False)
    note=forms.CharField(widget=forms.Textarea(attrs={"rows":3}),required=False)
    def clean(self):
        d=super().clean()
        if d.get("item_type")=="original" and not d.get("original"): self.add_error("original","Choose an original.")
        if d.get("item_type")=="print" and not d.get("print_option"): self.add_error("print_option","Choose a print option.")
        return d
    def save(self,user=None):
        d=self.cleaned_data; orig=d["original"] if d["item_type"]=="original" else None; opt=d["print_option"] if d["item_type"]=="print" else None
        return record_activity(kind=d["kind"],quantity=d["quantity"],activity_date=d["activity_date"],original_id=orig.pk if orig else None,print_option_id=opt.pk if opt else None,from_location_id=d["from_location"].pk if d["from_location"] else None,to_location_id=d["to_location"].pk if d["to_location"] else None,source=d["source"],reference=d["reference"],note=d["note"],user=user)
