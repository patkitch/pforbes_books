from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("art_inventory", "0002_separate_local_print_inventory")]
    operations = [
        migrations.AddField(
            model_name="inventoryactivity",
            name="refund_issued",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="inventoryactivity",
            name="kind",
            field=models.CharField(max_length=20, choices=[
                ("purchase", "Print stock added"),
                ("return", "Print returned to stock"),
                ("transfer", "Transfer"),
                ("local_sale", "Local print sale"),
                ("original_sale", "Original sold"),
                ("original_return", "Original returned"),
                ("gift", "Gift"),
                ("adjust_add", "Count adjustment — add"),
                ("adjust_remove", "Count adjustment — remove"),
                ("correction", "Record corrected"),
            ]),
        ),
        migrations.AlterField(
            model_name="artwork",
            name="support",
            field=models.CharField(blank=True, max_length=120, verbose_name="Painting surface", help_text="Canvas, paper, wood panel, or another painting surface."),
        ),
    ]
