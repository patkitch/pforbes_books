from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0002_wooorderimport")]
    operations = [
        migrations.AddField(model_name="importbatch", name="statement_summary",
                            field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name="importrow", name="source_details",
                            field=models.JSONField(default=dict, blank=True)),
    ]
