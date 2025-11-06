from django.db import migrations

def backfill_location_entity(apps, schema_editor):
    Location = apps.get_model('stockops', 'Location')
    EntityModel = apps.get_model('django_ledger', 'EntityModel')

    # Pick your real entity here. If you only have one, first() is fine.
    # TODO: pick the correct entity; using first() is fine if you truly have one.
    ent = EntityModel.objects.first()
    if ent:
        Location.objects.filter(entity__isnull=True).update(entity=ent)

class Migration(migrations.Migration):

    dependencies = [
        ('stockops', '0002_location_entity_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_location_entity, migrations.RunPython.noop),
    ]
