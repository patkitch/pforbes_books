from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("accounting_imports","0011_stripe_group_match"),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[migrations.CreateModel(name="StripeAdjustment",fields=[
        ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
        ("balance_id",models.CharField(max_length=180,unique=True)),
        ("refund_id",models.CharField(max_length=180,null=True,blank=True,unique=True)),
        ("payout_id",models.CharField(max_length=180)),
        ("day",models.DateField()),
        ("kind",models.CharField(max_length=20,choices=[("refund","Customer refund"),("fee","Processor fee / credit")])),
        *[(k,models.DecimalField(max_digits=14,decimal_places=2,default=0)) for k in ("artwork","shipping","tax")],
        *[(k,models.DecimalField(max_digits=14,decimal_places=2)) for k in ("amount","fee","net")],
        ("evidence",models.CharField(max_length=500)),
        ("created_at",models.DateTimeField(auto_now_add=True)),
        ("voided_at",models.DateTimeField(null=True,blank=True)),
        ("void_reason",models.CharField(max_length=500,blank=True)),
        ("payment",models.ForeignKey(null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name="adjustments",to="accounting_imports.stripepaymentimport")),
        ("created_by",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="stripe_adjustments",to=settings.AUTH_USER_MODEL)),
        ("voided_by",models.ForeignKey(null=True,blank=True,on_delete=django.db.models.deletion.PROTECT,related_name="voided_stripe_adjustments",to=settings.AUTH_USER_MODEL)),
    ])]
