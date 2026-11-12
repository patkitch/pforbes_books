from django.db import migrations, models

CANVAS_CHOICES = [
    ("traditional", "Traditional / Slim (0.5–0.75 in)"),
    ("gallery", "Gallery / Deep Edge (1.25–1.5 in)"),
    ("museum", "Museum / Ultra-Deep (2–2.5 in)"),
    ("flat", "Flat Panel / Board (0.125–0.25 in)"),
]
PRINT_CHOICES = [
    ("matted_8x10_4x6", "8 × 10 white mat (4 × 6 print)"),
    ("matted_11x14_8x10", "11 × 14 white mat (8 × 10 print)"),
    ("print_only_11x14", "11 × 14 print only (no mat)"),
]

class Migration(migrations.Migration):
    dependencies = [("art_inventory", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="original",
            name="canvas_profile",
            field=models.CharField(blank=True, choices=CANVAS_CHOICES, max_length=80),
        ),
        migrations.RemoveField(model_name="printoption", name="label"),
        migrations.RemoveField(model_name="printoption", name="width_inches"),
        migrations.RemoveField(model_name="printoption", name="height_inches"),
        migrations.RemoveField(model_name="printoption", name="format"),
        migrations.RemoveField(model_name="printoption", name="finish_details"),
        migrations.RemoveField(model_name="printoption", name="listing_status"),
        migrations.RemoveField(model_name="printoption", name="woo_product_id"),
        migrations.RemoveField(model_name="printoption", name="woo_url"),
        migrations.AddField(
            model_name="printoption",
            name="print_type",
            field=models.CharField(choices=PRINT_CHOICES, max_length=32, default="matted_11x14_8x10"),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="printoption",
            constraint=models.UniqueConstraint(fields=("artwork", "print_type"), name="artinv_unique_artwork_print_type"),
        ),
    ]
