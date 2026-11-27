from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0007_woo_payout_match"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="StripePaymentImport", fields=[
        ("id", models.BigAutoField(primary_key=True, serialize=False)),
        ("charge_id", models.CharField(max_length=180, unique=True)),
        ("created_utc", models.DateTimeField()),
        ("gross", models.DecimalField(max_digits=14, decimal_places=2)),
        ("fee", models.DecimalField(max_digits=14, decimal_places=2)),
        ("refunded", models.DecimalField(max_digits=14, decimal_places=2)),
        ("currency", models.CharField(max_length=3)),
        ("payment_status", models.CharField(max_length=40)),
        ("captured", models.BooleanField()),
        ("payout_id", models.CharField(max_length=180, blank=True)),
        ("woo_order_number", models.PositiveBigIntegerField(null=True, blank=True)),
        ("customer_name", models.CharField(max_length=200, blank=True)),
        ("customer_email", models.EmailField(max_length=254, blank=True)),
        ("customer_reference", models.CharField(max_length=180, blank=True)),
        ("description", models.CharField(max_length=500, blank=True)),
        ("source_details", models.JSONField(default=dict)),
        ("imported_at", models.DateTimeField(auto_now_add=True)),
        ("imported_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="imported_stripe_payments")),
    ], options={"ordering":["-created_utc","-pk"]})]
