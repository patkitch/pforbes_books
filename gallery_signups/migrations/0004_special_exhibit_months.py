from datetime import date

from django.db import migrations


def update_special_exhibit_months(apps, schema_editor):
    Event = apps.get_model("gallery_signups", "FeaturedArtistEvent")
    Slot = apps.get_model("gallery_signups", "FeaturedArtistSlot")

    special_months = [
        (date(2027, 6, 18), "Member-Hosted Exhibit"),
        (date(2027, 7, 16), "2027 Juried Show"),
    ]
    for event_date, label in special_months:
        event = Event.objects.filter(event_date=event_date).first()
        if not event:
            continue
        event.title = label
        event.save(update_fields=["title"])
        Slot.objects.filter(
            event=event,
            slot_type="artist",
            artist_name="",
            guest_application__isnull=True,
        ).update(reservation_label=label)

    august = Event.objects.filter(event_date=date(2027, 8, 20)).first()
    if august:
        if august.title in {"2027 Juried Show", "Juried Show", "Member-Hosted Exhibit"}:
            august.title = ""
            august.save(update_fields=["title"])
        Slot.objects.filter(
            event=august,
            slot_type="artist",
            artist_name="",
            guest_application__isnull=True,
            reservation_label__in=["2027 Juried Show", "Juried Show", "Member-Hosted Exhibit"],
        ).update(reservation_label="")


class Migration(migrations.Migration):
    dependencies = [
        ("gallery_signups", "0003_applications_signup_history"),
    ]

    operations = [
        migrations.RunPython(update_special_exhibit_months, migrations.RunPython.noop),
    ]
