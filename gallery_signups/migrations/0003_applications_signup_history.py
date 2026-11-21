import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gallery_signups", "0002_worker_slots"),
    ]

    operations = [
        migrations.CreateModel(
            name="GallerySignupChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_date", models.DateField()),
                ("slot_label", models.CharField(max_length=40)),
                ("action", models.CharField(choices=[
                    ("claimed", "Claimed"), ("changed", "Changed"), ("removed", "Removed"),
                    ("admin_edit", "Admin edit"), ("admin_clear", "Admin cleared"),
                    ("guest_approved", "Guest artist approved"),
                ], max_length=20)),
                ("old_name", models.CharField(blank=True, max_length=120)),
                ("new_name", models.CharField(blank=True, max_length=120)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-changed_at"]},
        ),
        migrations.CreateModel(
            name="GalleryArtistApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("artist_name", models.CharField(max_length=160)),
                ("address", models.TextField()),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(max_length=40)),
                ("medium", models.CharField(max_length=120)),
                ("artwork_url", models.URLField(blank=True)),
                ("wall_count", models.PositiveSmallIntegerField(default=1)),
                ("preferred_months", models.JSONField(default=list)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending review"), ("approved", "Approved"),
                    ("not_selected", "Not selected"),
                ], db_index=True, default="pending", max_length=20)),
                ("admin_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("selected_event", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="guest_artist_applications", to="gallery_signups.featuredartistevent",
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GalleryArtistApplicationImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="guest_artist_applications/%Y/")),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="images", to="gallery_signups.galleryartistapplication",
                )),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddField(
            model_name="featuredartistslot",
            name="guest_application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_slots",
                to="gallery_signups.galleryartistapplication",
            ),
        ),
    ]
