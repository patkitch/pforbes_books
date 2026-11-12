import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

CANVAS_PROFILES = [
    ("traditional", "Traditional / Slim (0.5–0.75 in)"),
    ("gallery", "Gallery / Deep Edge (1.25–1.5 in)"),
    ("museum", "Museum / Ultra-Deep (2–2.5 in)"),
    ("flat", "Flat Panel / Board (0.125–0.25 in)"),
]

class Location(models.Model):
    TYPES=[("home","Home"),("gallery","Gallery"),("show","Show / event"),("storage","Storage"),("transit","In transit"),("other","Other")]
    name=models.CharField(max_length=100,unique=True)
    kind=models.CharField(max_length=16,choices=TYPES,default="other")
    is_active=models.BooleanField(default=True)
    class Meta: ordering=["name"]
    def __str__(self): return self.name

class Artwork(models.Model):
    title=models.CharField(max_length=200)
    story=models.TextField(blank=True)
    style=models.CharField(max_length=100,blank=True)
    medium=models.CharField(max_length=100,blank=True)
    width_inches=models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True)
    height_inches=models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True)
    support=models.CharField(max_length=120,blank=True,verbose_name="Painting surface",help_text="Canvas, paper, wood panel, or another painting surface.")
    image_url=models.URLField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["title"]
    def __str__(self): return self.title

class Original(models.Model):
    STATUSES=[("available","Available"),("not_for_sale","Not for sale"),("sold","Sold"),("gifted","Gifted")]
    LISTINGS=[("not_listed","Not listed"),("draft","Draft"),("published","Published")]
    artwork=models.OneToOneField(Artwork,on_delete=models.CASCADE,related_name="original")
    sku=models.CharField(max_length=40,unique=True,blank=True)
    status=models.CharField(max_length=20,choices=STATUSES,default="available")
    location=models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    price=models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    canvas_profile=models.CharField(max_length=80,choices=CANVAS_PROFILES,blank=True)
    framed=models.BooleanField(default=False)
    outside_width_inches=models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True)
    outside_height_inches=models.DecimalField(max_digits=7,decimal_places=2,null=True,blank=True)
    listing_status=models.CharField(max_length=16,choices=LISTINGS,default="not_listed")
    woo_product_id=models.PositiveBigIntegerField(null=True,blank=True)
    woo_url=models.URLField(blank=True)
    def save(self,*a,**kw):
        if not self.sku: self.sku="PFA-O-"+uuid.uuid4().hex[:10].upper()
        super().save(*a,**kw)
    @property
    def on_hand(self): return int(self.status in ("available","not_for_sale"))
    def __str__(self): return self.artwork.title

class PrintOption(models.Model):
    PRINT_TYPES=[
        ("matted_8x10_4x6","8 × 10 white mat (4 × 6 print)"),
        ("matted_11x14_8x10","11 × 14 white mat (8 × 10 print)"),
        ("print_only_11x14","11 × 14 print only (no mat)"),
    ]
    artwork=models.ForeignKey(Artwork,on_delete=models.CASCADE,related_name="print_options")
    sku=models.CharField(max_length=40,unique=True,blank=True)
    print_type=models.CharField(max_length=32,choices=PRINT_TYPES)
    price=models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True,validators=[MinValueValidator(0)])
    is_active=models.BooleanField(default=True)
    class Meta:
        ordering=["artwork__title","print_type"]
        constraints=[models.UniqueConstraint(fields=["artwork","print_type"],name="artinv_unique_artwork_print_type")]
    def save(self,*a,**kw):
        if not self.sku: self.sku="PFA-P-"+uuid.uuid4().hex[:10].upper()
        super().save(*a,**kw)
    def __str__(self): return f"{self.artwork.title} — {self.get_print_type_display()}"

class PrintStock(models.Model):
    print_option=models.ForeignKey(PrintOption,on_delete=models.CASCADE,related_name="stock")
    location=models.ForeignKey(Location,on_delete=models.PROTECT,related_name="print_stock")
    quantity=models.PositiveIntegerField(default=0)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["print_option","location"],name="artinv_unique_print_stock_place")]
    def __str__(self): return f"{self.print_option} at {self.location}: {self.quantity}"

class InventoryActivity(models.Model):
    KINDS=[
        ("purchase","Print stock added"),("return","Print returned to stock"),("transfer","Transfer"),
        ("local_sale","Local print sale"),("original_sale","Original sold"),("original_return","Original returned"),
        ("gift","Gift"),("adjust_add","Count adjustment — add"),("adjust_remove","Count adjustment — remove"),
        ("correction","Record corrected"),
    ]
    original=models.ForeignKey(Original,null=True,blank=True,on_delete=models.PROTECT,related_name="activities")
    print_option=models.ForeignKey(PrintOption,null=True,blank=True,on_delete=models.PROTECT,related_name="activities")
    kind=models.CharField(max_length=20,choices=KINDS)
    quantity=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    activity_date=models.DateField()
    from_location=models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT,related_name="activities_from")
    to_location=models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT,related_name="activities_to")
    source=models.CharField(max_length=100,blank=True)
    reference=models.CharField(max_length=100,blank=True)
    note=models.TextField(blank=True)
    refund_issued=models.BooleanField(default=False)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-activity_date","-created_at"]
        constraints=[
            models.CheckConstraint(condition=Q(original__isnull=False,print_option__isnull=True)|Q(original__isnull=True,print_option__isnull=False),name="artinv_activity_one_item"),
            models.CheckConstraint(condition=Q(quantity__gte=1),name="artinv_activity_positive_qty"),
        ]
