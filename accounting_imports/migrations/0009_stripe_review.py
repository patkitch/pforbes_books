from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0008_stripe_payment_import")]
    operations = [
        migrations.AddField(model_name="stripepaymentimport", name="review_data", field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name="stripepaymentimport", name="review_history", field=models.JSONField(default=list, blank=True)),
    ]
