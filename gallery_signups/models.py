from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class GallerySettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    member_password_hash = models.CharField(max_length=128, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def set_member_password(self, raw):
        self.member_password_hash = make_password(raw)

    def check_member_password(self, raw):
        return bool(self.member_password_hash) and check_password(raw, self.member_password_hash)


class FeaturedArtistEvent(models.Model):
    event_date = models.DateField(unique=True)
    year = models.PositiveSmallIntegerField(default=2027, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["event_date"]

    def __str__(self):
        return self.event_date.strftime("%B %Y")


class FeaturedArtistSlot(models.Model):
    SLOT_TYPES = [("artist", "Featured Artist"), ("worker", "Worker")]

    event = models.ForeignKey(FeaturedArtistEvent, on_delete=models.CASCADE, related_name="slots")
    slot_type = models.CharField(max_length=12, choices=SLOT_TYPES, default="artist")
    position = models.PositiveSmallIntegerField()
    artist_name = models.CharField(max_length=120, blank=True)
    reservation_label = models.CharField(max_length=120, blank=True)
    guest_application = models.ForeignKey(
        "GalleryArtistApplication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_slots",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event__event_date", "slot_type", "position"]
        constraints = [
            models.UniqueConstraint(fields=["event", "slot_type", "position"], name="gallery_unique_type_pos"),
            models.CheckConstraint(
                condition=(
                    models.Q(slot_type="artist", position__in=[1, 2])
                    | models.Q(slot_type="worker", position__in=[1, 2, 3, 4])
                ),
                name="gallery_type_pos_check",
            ),
            models.CheckConstraint(condition=models.Q(artist_name="") | models.Q(reservation_label=""), name="gallery_slot_name_or_reservation"),
        ]

    @property
    def is_open(self):
        return not self.event.is_closed and not self.artist_name and not self.reservation_label

    @property
    def display_name(self):
        return self.reservation_label or self.artist_name

    @property
    def slot_label(self):
        if self.slot_type == "artist":
            return f"Featured Artist {self.position}"
        return f"Worker {self.position}"


class GalleryAdministrator(models.Model):
    username = models.CharField(max_length=80, unique=True)
    password_hash = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["username"]

    def set_password(self, raw):
        self.password_hash = make_password(raw)

    def check_password(self, raw):
        return check_password(raw, self.password_hash)


class GallerySignupChange(models.Model):
    ACTIONS = [
        ("claimed", "Claimed"),
        ("changed", "Changed"),
        ("removed", "Removed"),
        ("admin_edit", "Admin edit"),
        ("admin_clear", "Admin cleared"),
        ("guest_approved", "Guest artist approved"),
    ]
    event_date = models.DateField()
    slot_label = models.CharField(max_length=40)
    action = models.CharField(max_length=20, choices=ACTIONS)
    old_name = models.CharField(max_length=120, blank=True)
    new_name = models.CharField(max_length=120, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.event_date:%B %Y} {self.slot_label}: {self.get_action_display()}"


class GalleryArtistApplication(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending review"),
        ("approved", "Approved"),
        ("not_selected", "Not selected"),
    ]
    artist_name = models.CharField(max_length=160)
    address = models.TextField()
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    medium = models.CharField(max_length=120)
    artwork_url = models.URLField(blank=True)
    wall_count = models.PositiveSmallIntegerField(default=1)
    preferred_months = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    selected_event = models.ForeignKey(
        FeaturedArtistEvent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="guest_artist_applications",
    )
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.artist_name} — {self.get_status_display()}"


class GalleryArtistApplicationImage(models.Model):
    application = models.ForeignKey(
        GalleryArtistApplication, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="guest_artist_applications/%Y/")
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
