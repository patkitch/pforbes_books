from datetime import date
from django.db import migrations, models
import django.db.models.deletion

def seed_2027_calendar(apps, schema_editor):
    Event = apps.get_model("gallery_signups", "FeaturedArtistEvent")
    Slot = apps.get_model("gallery_signups", "FeaturedArtistSlot")
    dates = [date(2027,1,15),date(2027,2,19),date(2027,3,19),date(2027,4,16),date(2027,5,21),date(2027,6,18),date(2027,7,16),date(2027,8,20),date(2027,9,17),date(2027,10,15),date(2027,11,19),date(2027,12,17)]
    for day in dates:
        event, _ = Event.objects.get_or_create(event_date=day, defaults={"year": 2027})
        for position in (1, 2):
            Slot.objects.get_or_create(event=event, position=position)

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="FeaturedArtistEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event_date", models.DateField(unique=True)), ("year", models.PositiveSmallIntegerField(db_index=True, default=2027)),
            ("title", models.CharField(blank=True, max_length=120)), ("is_closed", models.BooleanField(default=False)),
        ], options={"ordering": ["event_date"]}),
        migrations.CreateModel(name="GalleryAdministrator", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("username", models.CharField(max_length=80, unique=True)), ("password_hash", models.CharField(max_length=128)),
            ("is_active", models.BooleanField(default=True)),
        ], options={"ordering": ["username"]}),
        migrations.CreateModel(name="GallerySettings", fields=[
            ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
            ("member_password_hash", models.CharField(blank=True, max_length=128)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="FeaturedArtistSlot", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("position", models.PositiveSmallIntegerField()), ("artist_name", models.CharField(blank=True, max_length=120)),
            ("reservation_label", models.CharField(blank=True, max_length=120)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="slots", to="gallery_signups.featuredartistevent")),
        ], options={"ordering": ["event__event_date", "position"]}),
        migrations.AddConstraint(model_name="featuredartistslot", constraint=models.UniqueConstraint(fields=("event", "position"), name="gallery_unique_event_slot")),
        migrations.AddConstraint(model_name="featuredartistslot", constraint=models.CheckConstraint(condition=models.Q(("position__in", [1, 2])), name="gallery_slot_position_1_2")),
        migrations.AddConstraint(model_name="featuredartistslot", constraint=models.CheckConstraint(condition=models.Q(("artist_name", "")) | models.Q(("reservation_label", "")), name="gallery_slot_name_or_reservation")),
        migrations.RunPython(seed_2027_calendar, migrations.RunPython.noop),
    ]
