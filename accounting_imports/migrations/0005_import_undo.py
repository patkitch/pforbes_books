from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0004_bank_review"),
                    migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="importbatch", name="undone_at",
                            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="importbatch", name="undone_by",
                            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True,
                                related_name="undone_import_batches", on_delete=django.db.models.deletion.SET_NULL)),
        migrations.AddField(model_name="importbatch", name="undone_count",
                            field=models.PositiveIntegerField(default=0)),
    ]
