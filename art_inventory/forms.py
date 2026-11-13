from django import forms
from django.db import transaction
from django.utils import timezone
from .models import Artwork,CANVAS_PROFILES,InventoryActivity,Location,Original,PrintOption
from .services import record_activity

class ArtworkForm(forms.ModelForm):
    initial_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False,help_text="Where the original is right now.")
    price=forms.DecimalField(max_digits=10,decimal_places=2,min_value=0,required=False,help_text="Optional asking price.")
    canvas_profile=forms.ChoiceField(choices=[("", "Select canvas type / profile")]+CANVAS_PROFILES,required=True,help_text="Choose the canvas edge depth or panel type.")
    framed=forms.BooleanField(required=False)
    outside_width_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False,help_text="Include the frame, if there is one.")
    outside_height_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False,help_text="Include the frame, if there is one.")
    class Meta:
        model=Artwork
        fields=["title","story","style","medium","width_inches","height_inches","support","image_url"]
        widgets={"story":forms.Textarea(attrs={"rows":4})}
    def save(self,commit=True):
        art=super().save(commit=commit)
        if commit: Original.objects.create(artwork=art,location=self.cleaned_data.get("initial_location"),price=self.cleaned_data.get("price"),canvas_profile=self.cleaned_data.get("canvas_profile",""),framed=self.cleaned_data.get("framed",False),outside_width_inches=self.cleaned_data.get("outside_width_inches"),outside_height_inches=self.cleaned_data.get("outside_height_inches"))
        return art

class ArtworkEditForm(forms.Form):
    story=forms.CharField(required=False,widget=forms.Textarea(attrs={"rows":4}))
    style=forms.CharField(max_length=100,required=False)
    medium=forms.CharField(max_length=100,required=False)
    width_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    height_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    support=forms.CharField(max_length=120,required=False,label="Painting surface",help_text="Canvas, paper, wood panel, or another painting surface.")
    image_url=forms.URLField(required=False)
    sku=forms.CharField(max_length=40,label="SKU")
    status=forms.ChoiceField(choices=Original.STATUSES)
    location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False)
    price=forms.DecimalField(max_digits=10,decimal_places=2,min_value=0,required=False)
    canvas_profile=forms.ChoiceField(choices=[("", "Not recorded")]+CANVAS_PROFILES)
    framed=forms.BooleanField(required=False)
    outside_width_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    outside_height_inches=forms.DecimalField(max_digits=7,decimal_places=2,min_value=0,required=False)
    listing_status=forms.ChoiceField(choices=Original.LISTINGS)
    woo_product_id=forms.IntegerField(min_value=1,required=False)
    woo_url=forms.URLField(required=False)
    def __init__(self,*args,artwork,original,**kwargs):
        self.artwork=artwork; self.original=original
        super().__init__(*args,initial={
            "story":artwork.story,"style":artwork.style,"medium":artwork.medium,"width_inches":artwork.width_inches,
            "height_inches":artwork.height_inches,"support":artwork.support,"image_url":artwork.image_url,
            "sku":original.sku,"status":original.status,"location":original.location_id,"price":original.price,
            "canvas_profile":original.canvas_profile,"framed":original.framed,
            "outside_width_inches":original.outside_width_inches,"outside_height_inches":original.outside_height_inches,
            "listing_status":original.listing_status,"woo_product_id":original.woo_product_id,"woo_url":original.woo_url,
        },**kwargs)
    def clean(self):
        d=super().clean()
        if self.original.status=="sold" and d.get("status")=="available":
            self.add_error("status","Use Record activity → Original returned so the return location and refund can be recorded.")
        return d
    @transaction.atomic
    def save(self,user=None):
        d=self.cleaned_data; original=self.original
        old_location=original.location
        def snapshot():
            return {
                "Artist story": self.artwork.story, "Style": self.artwork.style, "Medium": self.artwork.medium,
                "Width": self.artwork.width_inches, "Height": self.artwork.height_inches,
                "Painting surface": self.artwork.support, "Image URL": self.artwork.image_url,
                "SKU": original.sku, "Status": original.get_status_display(), "Location": str(original.location or ""),
                "Price": original.price, "Canvas profile": original.get_canvas_profile_display(),
                "Framed": original.framed, "Outside width": original.outside_width_inches,
                "Outside height": original.outside_height_inches, "Listing status": original.get_listing_status_display(),
                "Woo product ID": original.woo_product_id, "Woo URL": original.woo_url,
            }
        before=snapshot()
        for name in ("story","style","medium","width_inches","height_inches","support","image_url"):
            setattr(self.artwork,name,d[name])
        self.artwork.save()
        for name in ("sku","status","location","price","canvas_profile","framed","outside_width_inches","outside_height_inches","listing_status","woo_product_id","woo_url"):
            setattr(original,name,d[name])
        original.save()
        after=snapshot()
        def shown(value):
            if value in (None, ""): return "(blank)"
            if isinstance(value, bool): return "Yes" if value else "No"
            return str(value)
        changes=[f"{label}: {shown(before[label])} -> {shown(after[label])}" for label in before if before[label]!=after[label]]
        if changes:
            InventoryActivity.objects.create(kind="correction",quantity=1,activity_date=timezone.localdate(),original=original,from_location=old_location,to_location=original.location,note="Record edited. "+"; ".join(changes),created_by=user if getattr(user,"is_authenticated",False) else None)
        return self.artwork

class PrintOptionForm(forms.Form):
    artwork=forms.ModelChoiceField(queryset=Artwork.objects.all(),label="Artwork title")
    print_type=forms.ChoiceField(choices=[("", "Select print size / type")]+PrintOption.PRINT_TYPES,label="Print type you order",help_text="Choose the exact format you ordered.")
    price=forms.DecimalField(max_digits=10,decimal_places=2,min_value=0,required=False,label="Your selling price",help_text="Optional; this does not change the stock count.")
    quantity=forms.IntegerField(min_value=0,initial=0,label="Prints currently on hand",help_text="Enter the number you have now.")
    location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False,label="Where are these prints?",help_text="Choose where this starting quantity is stored.")
    def clean(self):
        data=super().clean()
        if data.get("quantity",0)>0 and not data.get("location"): self.add_error("location","Choose where the prints are.")
        if data.get("artwork") and data.get("print_type") and PrintOption.objects.filter(artwork=data["artwork"],print_type=data["print_type"]).exists(): self.add_error("print_type","This print size is already set up. Use Record activity to add stock.")
        return data
    @transaction.atomic
    def save(self,user=None):
        option=PrintOption.objects.create(artwork=self.cleaned_data["artwork"],print_type=self.cleaned_data["print_type"],price=self.cleaned_data.get("price"))
        if self.cleaned_data.get("quantity",0):
            record_activity(kind="purchase",quantity=self.cleaned_data["quantity"],activity_date=timezone.localdate(),print_option_id=option.pk,to_location_id=self.cleaned_data["location"].pk,source="Initial count",note="Starting on-hand quantity",user=user)
        return option

class ActivityForm(forms.Form):
    item_type=forms.ChoiceField(choices=[("original","Original"),("print","Print option")],help_text="Choose whether this activity is for a painting or print stock.")
    original=forms.ModelChoiceField(queryset=Original.objects.select_related("artwork").order_by("artwork__title","sku"),required=False,label="Original artwork",help_text="Select the painting affected by this activity.")
    print_option=forms.ModelChoiceField(queryset=PrintOption.objects.select_related("artwork").filter(is_active=True),required=False,label="Print size",help_text="Select the specific print format affected.")
    kind=forms.ChoiceField(choices=[(k,{"local_sale":"Print sold","adjust_remove":"Reduce print stock (other reason)"}.get(k,v)) for k,v in InventoryActivity.KINDS if k!="correction"],label="Status",help_text="Choose what happened: sale, return, transfer, or count correction.")
    quantity=forms.IntegerField(min_value=1,initial=1,help_text="Number of prints, or 1 for an original.")
    activity_date=forms.DateField(label="Date of sale or inventory change",initial=timezone.localdate,widget=forms.DateInput(attrs={"type":"date"}))
    from_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False,label="From location",help_text="Where the item was sold or moved from.")
    to_location=forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True),required=False,label="To location",help_text="Where the item was returned or moved to.")
    refund_issued=forms.BooleanField(required=False,label="Refund issued",help_text="Check this if you returned the buyer’s money.")
    source=forms.CharField(max_length=100,required=False,help_text="Where it happened, such as the gallery, a show, or the website.")
    reference=forms.CharField(max_length=100,required=False,help_text="Optional receipt or order number; leave blank if there is none.")
    note=forms.CharField(label="Reason / notes",help_text="For a print sale or stock reduction, say why (for example: sold at gallery).",widget=forms.Textarea(attrs={"rows":3}),required=False)
    def clean(self):
        d=super().clean()
        if d.get("item_type")=="original" and not d.get("original"): self.add_error("original","Choose an original.")
        if d.get("item_type")=="print" and not d.get("print_option"): self.add_error("print_option","Choose a print option.")
        if d.get("kind")=="original_return" and not d.get("to_location"): self.add_error("to_location","Choose where the returned original is now.")
        if d.get("item_type")=="print" and d.get("kind") in ("local_sale","adjust_remove") and not d.get("note","").strip(): self.add_error("note","Enter a reason for reducing the print quantity.")
        if d.get("item_type")=="print" and d.get("refund_issued"): self.add_error("refund_issued","Refund tracking is for original returns.")
        return d
    def save(self,user=None):
        d=self.cleaned_data; orig=d["original"] if d["item_type"]=="original" else None; opt=d["print_option"] if d["item_type"]=="print" else None
        return record_activity(kind=d["kind"],quantity=d["quantity"],activity_date=d["activity_date"],original_id=orig.pk if orig else None,print_option_id=opt.pk if opt else None,from_location_id=d["from_location"].pk if d["from_location"] else None,to_location_id=d["to_location"].pk if d["to_location"] else None,source=d["source"],reference=d["reference"],note=d["note"],refund_issued=d["refund_issued"],user=user)
