from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_supply_rows(apps, schema_editor):
    Supply = apps.get_model("art_inventory", "StudioSupply")
    for size in ("8x10", "11x14"):
        for supply_type in ("bag", "backing_board", "mat"):
            Supply.objects.get_or_create(
                size=size,
                supply_type=supply_type,
                defaults={"quantity_on_hand": 0},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("art_inventory", "0003_returns_and_activity_notes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StudioSupply",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("size", models.CharField(max_length=8, choices=[("8x10", "8 × 10 in"), ("11x14", "11 × 14 in")])),
                ("supply_type", models.CharField(max_length=20, choices=[("bag", "Bag"), ("backing_board", "Backing board"), ("mat", "Mat")])),
                ("quantity_on_hand", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["size", "supply_type"]},
        ),
        migrations.CreateModel(
            name="StudioSupplyActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=12, choices=[("received", "Supplies received"), ("used", "Supplies used"), ("count", "Count corrected")])),
                ("quantity", models.PositiveIntegerField()),
                ("activity_date", models.DateField()),
                ("note", models.CharField(max_length=240, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL)),
                ("supply", models.ForeignKey(to="art_inventory.studiosupply", related_name="activities", on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={"ordering": ["-activity_date", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="studiosupply",
            constraint=models.UniqueConstraint(fields=("size", "supply_type"), name="artinv_unique_supply_size_type"),
        ),
        migrations.RunPython(seed_supply_rows, migrations.RunPython.noop),
    ]
