from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_contacts", "0002_receiptitem")]
    operations = [
        migrations.AddField(
            model_name="receipt",
            name="woo_snapshot",
            field=models.JSONField(default=dict, blank=True, editable=False),
        ),
    ]
