from datetime import date

from django.db import migrations


def open_june_featured_artist_walls(apps, schema_editor):
    Event = apps.get_model("gallery_signups", "FeaturedArtistEvent")
    Slot = apps.get_model("gallery_signups", "FeaturedArtistSlot")

    june = Event.objects.filter(event_date=date(2027, 6, 18)).first()
    if not june:
        return

    if june.title in {"Member-Hosted Exhibit", "Wanda - group glass exhibit"}:
        june.title = ""
        june.save(update_fields=["title"])

    Slot.objects.filter(
        event=june,
        slot_type="artist",
        artist_name="",
        guest_application__isnull=True,
        reservation_label__in=["Member-Hosted Exhibit", "Wanda - group glass exhibit"],
    ).update(reservation_label="")


class Migration(migrations.Migration):
    dependencies = [
        ("gallery_signups", "0005_correct_june_exhibit_label"),
    ]

    operations = [
        migrations.RunPython(open_june_featured_artist_walls, migrations.RunPython.noop),
    ]
