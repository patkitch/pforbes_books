from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="WooOrderImport",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("source_order_id", models.PositiveBigIntegerField(unique=True)),
                ("order_date", models.DateField()),
                ("woo_status", models.CharField(max_length=30)),
                ("customer_name", models.CharField(max_length=200, blank=True)),
                ("payment_method", models.CharField(max_length=120, blank=True)),
                ("payment_reference", models.CharField(max_length=180, blank=True)),
                ("total", models.DecimalField(max_digits=14, decimal_places=2)),
                ("tax_total", models.DecimalField(max_digits=14, decimal_places=2, default=0)),
                ("shipping_total", models.DecimalField(max_digits=14, decimal_places=2, default=0)),
                ("payload", models.JSONField()),
                ("review_status", models.CharField(max_length=12, default="pending", choices=[
                    ("pending", "Pending review"), ("excluded", "Excluded"), ("receipted", "Internal receipt created"),
                ])),
                ("receipt_id", models.PositiveBigIntegerField(null=True, blank=True)),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
            ],
            options={"ordering": ["-order_date", "-pk"]},
        ),
    ]
