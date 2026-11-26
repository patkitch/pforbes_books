from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0003_bank_source_details")]
    operations = [
        migrations.AddField(model_name="importrow", name="review_data",
                            field=models.JSONField(default=dict, blank=True)),
        migrations.AlterField(model_name="importrow", name="status",
            field=models.CharField(max_length=12, default="pending",
                choices=[("pending", "Pending"), ("excluded", "Excluded"),
                         ("reviewed", "Reviewed — not posted")])),
    ]
