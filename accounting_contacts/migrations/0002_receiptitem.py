from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting_contacts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ReceiptItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField(default=1)),
                ("artwork_title", models.CharField(max_length=200)),
                ("item_type", models.CharField(
                    choices=[("original", "Original artwork"), ("print", "Fine art print"), ("other", "Other item")],
                    max_length=16
                )),
                ("size", models.CharField(blank=True, help_text="For example, 11x14 print or 24x36 original.", max_length=80)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("receipt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="accounting_contacts.receipt")),
            ],
            options={"ordering": ("position", "pk")},
        )
    ]
