from datetime import date

from django.db import migrations


def correct_june_exhibit_label(apps, schema_editor):
    Event = apps.get_model("gallery_signups", "FeaturedArtistEvent")
    Slot = apps.get_model("gallery_signups", "FeaturedArtistSlot")

    june = Event.objects.filter(event_date=date(2027, 6, 18)).first()
    if not june:
        return

    if june.title == "Member-Hosted Exhibit":
        june.title = "Wanda - group glass exhibit"
        june.save(update_fields=["title"])

    Slot.objects.filter(
        event=june,
        slot_type="artist",
        reservation_label="Member-Hosted Exhibit",
    ).update(reservation_label="Wanda - group glass exhibit")


class Migration(migrations.Migration):
    dependencies = [
        ("gallery_signups", "0004_special_exhibit_months"),
    ]

    operations = [
        migrations.RunPython(correct_june_exhibit_label, migrations.RunPython.noop),
    ]
