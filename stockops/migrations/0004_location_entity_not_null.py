from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('stockops', '0003_backfill_location_entity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='location',
            name='entity',
            field=models.ForeignKey(
                to='django_ledger.entitymodel',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='locations',
                null=False,
                blank=False,
            ),
        ),
    ]
