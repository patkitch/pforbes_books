from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ImportBatch",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("account_id", models.PositiveBigIntegerField()),
                ("filename", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="ImportRow",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("account_id", models.PositiveBigIntegerField()),
                ("transaction_date", models.DateField()),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("fingerprint", models.CharField(max_length=64)),
                ("occurrence", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(
                    choices=[("pending", "Pending"), ("excluded", "Excluded")],
                    default="pending", max_length=12,
                )),
                ("note", models.CharField(blank=True, max_length=255)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="rows", to="accounting_imports.importbatch",
                )),
            ],
            options={"ordering": ["transaction_date", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.UniqueConstraint(
                fields=("account_id", "fingerprint", "occurrence"),
                name="unique_import_row_per_account_occurrence",
            ),
        ),
    ]
