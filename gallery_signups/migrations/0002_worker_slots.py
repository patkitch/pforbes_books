from django.db import migrations, models
import django.db.models


def seed_2027_worker_slots(apps, schema_editor):
    Event = apps.get_model("gallery_signups", "FeaturedArtistEvent")
    Slot = apps.get_model("gallery_signups", "FeaturedArtistSlot")
    for event in Event.objects.filter(year=2027).iterator():
        for position in range(1, 5):
            Slot.objects.get_or_create(
                event=event,
                slot_type="worker",
                position=position,
                defaults={"artist_name": "", "reservation_label": ""},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("gallery_signups", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="featuredartistslot",
            name="slot_type",
            field=models.CharField(
                choices=[("artist", "Featured Artist"), ("worker", "Worker")],
                default="artist",
                max_length=12,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="featuredartistslot",
            name="gallery_unique_event_slot",
        ),
        migrations.RemoveConstraint(
            model_name="featuredartistslot",
            name="gallery_slot_position_1_2",
        ),
        migrations.AddConstraint(
            model_name="featuredartistslot",
            constraint=models.UniqueConstraint(
                fields=("event", "slot_type", "position"),
                name="gallery_unique_type_pos",
            ),
        ),
        migrations.AddConstraint(
            model_name="featuredartistslot",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(slot_type="artist", position__in=[1, 2])
                    | models.Q(slot_type="worker", position__in=[1, 2, 3, 4])
                ),
                name="gallery_type_pos_check",
            ),
        ),
        migrations.RunPython(seed_2027_worker_slots, migrations.RunPython.noop),
    ]
