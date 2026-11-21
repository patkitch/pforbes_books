import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import redirect_to_login
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    AdminLoginForm, AdministratorForm, ApplicationDecisionForm, ClaimSlotForm,
    EventEditForm, GalleryArtistApplicationForm, MemberPasswordForm,
    MemberSettingsForm, SlotEditForm,
)
from .models import (
    FeaturedArtistEvent, FeaturedArtistSlot, GalleryAdministrator,
    GalleryArtistApplication, GalleryArtistApplicationImage,
    GallerySettings, GallerySignupChange,
)

logger = logging.getLogger(__name__)


def _member_allowed(request):
    return request.session.get("gallery_member_access") is True


def _admin_account(request):
    key = request.session.get("gallery_admin_id")
    return GalleryAdministrator.objects.filter(pk=key, is_active=True).first() if key else None


def _admin_allowed(request):
    return (request.user.is_authenticated and request.user.is_superuser) or _admin_account(request) is not None


def _send_application_email(subject, body, to):
    if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        logger.warning("Artist application email not sent because SMTP is not configured.")
        return False
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        return True
    except Exception:
        logger.exception("Could not send artist application email.")
        return False


def _record_change(slot, action, old_name="", new_name=""):
    GallerySignupChange.objects.create(
        event_date=slot.event.event_date,
        slot_label=slot.slot_label,
        action=action,
        old_name=old_name or "",
        new_name=new_name or "",
    )


def member_login(request):
    settings_row = GallerySettings.current()
    form = MemberPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if settings_row.check_member_password(form.cleaned_data["password"]):
            logout(request)
            request.session.flush()
            request.session["gallery_member_access"] = True
            request.session.set_expiry(60 * 60 * 24 * 14)
            return redirect("gallery_signups:calendar")
        form.add_error("password", "That password did not match. Please check with Patricia.")
    return render(request, "gallery_signups/member_login.html", {
        "form": form, "configured": bool(settings_row.member_password_hash)
    })


def member_logout(request):
    request.session.pop("gallery_member_access", None)
    return redirect("gallery_signups:member_login")


def calendar(request, year=2027):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    events = FeaturedArtistEvent.objects.filter(year=year).prefetch_related("slots")
    for event in events:
        slots = list(event.slots.all())
        event.artist_slots = [slot for slot in slots if slot.slot_type == "artist"]
        event.worker_slots = [slot for slot in slots if slot.slot_type == "worker"]
        event.open_artist_count = sum(1 for slot in event.artist_slots if slot.is_open)
        event.open_worker_count = sum(1 for slot in event.worker_slots if slot.is_open)
        event.is_full = not event.open_artist_count and not event.open_worker_count
    return render(request, "gallery_signups/calendar.html", {"events": events, "year": year})


def month_detail(request, event_id):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    event = get_object_or_404(
        FeaturedArtistEvent.objects.prefetch_related("slots"), pk=event_id, year=2027
    )
    return render(request, "gallery_signups/month.html", {"event": event})


@require_POST
def claim_slot(request, slot_id):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    form = ClaimSlotForm(request.POST)
    slot = get_object_or_404(FeaturedArtistSlot.objects.select_related("event"), pk=slot_id)
    if form.is_valid():
        with transaction.atomic():
            slot = get_object_or_404(
                FeaturedArtistSlot.objects.select_for_update().select_related("event"), pk=slot_id
            )
            if slot.is_open:
                name = form.cleaned_data["name"]
                slot.artist_name = name
                slot.save(update_fields=["artist_name", "updated_at"])
                _record_change(slot, "claimed", new_name=name)
            else:
                messages.error(request, "That spot was just filled. Please choose another open spot.")
    else:
        messages.error(request, "Please enter your name.")
    return redirect("gallery_signups:month", event_id=slot.event_id)


@require_POST
def change_slot(request, slot_id):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    slot = get_object_or_404(
        FeaturedArtistSlot.objects.select_related("event"), pk=slot_id, slot_type__in=["artist", "worker"]
    )
    if slot.event.is_closed:
        messages.error(request, "This month is closed for changes. Please contact Patricia.")
        return redirect("gallery_signups:month", event_id=slot.event_id)
    if slot.guest_application_id or slot.reservation_label:
        messages.error(request, "Please contact Patricia to change this reserved spot.")
        return redirect("gallery_signups:month", event_id=slot.event_id)
    new_name = request.POST.get("name", "").strip()[:120]
    with transaction.atomic():
        slot = get_object_or_404(
            FeaturedArtistSlot.objects.select_for_update().select_related("event"), pk=slot_id
        )
        if slot.event.is_closed:
            messages.error(request, "This month is closed for changes. Please contact Patricia.")
            return redirect("gallery_signups:month", event_id=slot.event_id)
        if slot.guest_application_id or slot.reservation_label:
            messages.error(request, "Please contact Patricia to change this reserved spot.")
            return redirect("gallery_signups:month", event_id=slot.event_id)
        old_name = slot.artist_name
        if old_name:
            if new_name:
                slot.artist_name = new_name
                slot.save(update_fields=["artist_name", "updated_at"])
                _record_change(slot, "changed", old_name=old_name, new_name=new_name)
            else:
                slot.artist_name = ""
                slot.save(update_fields=["artist_name", "updated_at"])
                _record_change(slot, "removed", old_name=old_name)
    return redirect("gallery_signups:month", event_id=slot.event_id)
def public_artist_calendar(request, year=2027):
    events = FeaturedArtistEvent.objects.filter(year=year).prefetch_related("slots")
    for event in events:
        event.artist_slots = [slot for slot in event.slots.all() if slot.slot_type == "artist"]
        event.open_wall_count = sum(1 for slot in event.artist_slots if slot.is_open)
        event.is_full = event.is_closed or not event.open_wall_count
    return render(request, "gallery_signups/public_calendar.html", {"events": events, "year": year})


def artist_information(request):
    return render(request, "gallery_signups/artist_information.html")


def artist_application(request):
    form = GalleryArtistApplicationForm(request.POST or None, request.FILES or None)
    initial_month = request.GET.get("month")
    if request.method == "GET" and initial_month:
        try:
            event = FeaturedArtistEvent.objects.get(pk=int(initial_month), year=2027)
            form.fields["preferred_months"].initial = [event.pk]
        except (ValueError, FeaturedArtistEvent.DoesNotExist):
            pass

    if request.method == "POST" and form.is_valid():
        application = GalleryArtistApplication.objects.create(
            artist_name=form.cleaned_data["artist_name"].strip(),
            address=form.cleaned_data["address"].strip(),
            email=form.cleaned_data["email"].strip(),
            phone=form.cleaned_data["phone"].strip(),
            medium=form.cleaned_data["medium"].strip(),
            artwork_url=form.cleaned_data["artwork_url"].strip(),
            wall_count=int(form.cleaned_data["wall_count"]),
            preferred_months=[event.pk for event in form.cleaned_data["preferred_months"]],
        )
        for uploaded in form.cleaned_data["images"]:
            GalleryArtistApplicationImage.objects.create(
                application=application,
                image=uploaded,
                original_name=uploaded.name[:255],
            )

        admin_link = request.build_absolute_uri(
            reverse("gallery_signups:application_detail", args=[application.pk])
        )
        months = ", ".join(
            event.strftime("%B %Y") for event in
            FeaturedArtistEvent.objects.filter(pk__in=application.preferred_months).values_list("event_date", flat=True)
        )
        admin_notified = _send_application_email(
            f"New outside artist application #{application.pk}",
            f"{application.artist_name} submitted an application for {application.wall_count} wall(s). "
            f"Preferred months: {months}. Review it in the private signup admin: {admin_link}",
            getattr(settings, "GALLERY_ADMIN_EMAIL", "patriciaforbes@pforbesart.com"),
        )
        applicant_notified = _send_application_email(
            "Images Art Gallery received your Featured Artist request",
            f"Hello {application.artist_name},\n\nWe received your request for a guest Featured Artist wall. "
            "Your request is pending gallery review; submitting an application does not reserve a wall. "
            "We will contact you after a decision. The gallery's existing contract and payment terms apply.\n\n"
            "Images Art Gallery",
            application.email,
        )
        return render(request, "gallery_signups/application_received.html", {
            "application": application,
            "email_sent": applicant_notified,
            "admin_notified": admin_notified,
        })
    return render(request, "gallery_signups/artist_application.html", {"form": form})


def _application_admin_context(application):
    return {
        "application": application,
        "preferred_events": FeaturedArtistEvent.objects.filter(
            pk__in=application.preferred_months
        ).order_by("event_date"),
        "decision_form": ApplicationDecisionForm(application=application),
    }


def application_list(request):
    if not _admin_allowed(request):
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    applications = GalleryArtistApplication.objects.prefetch_related("images").select_related("selected_event")
    for application in applications:
        application.requested_months = FeaturedArtistEvent.objects.filter(
            pk__in=application.preferred_months
        ).order_by("event_date")
    return render(request, "gallery_signups/application_list.html", {
        "applications": applications,
        "pending_count": applications.filter(status="pending").count(),
    })


def application_detail(request, application_id):
    if not _admin_allowed(request):
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    application = get_object_or_404(
        GalleryArtistApplication.objects.prefetch_related("images"), pk=application_id
    )
    return render(request, "gallery_signups/application_detail.html", _application_admin_context(application))


@require_POST
def delete_application(request, application_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    application = get_object_or_404(
        GalleryArtistApplication, pk=application_id, status__in=["pending", "not_selected"]
    )
    # Remove uploaded objects before deleting the record. If storage deletion
    # fails, keep the application so an administrator can retry.
    for artwork in application.images.all():
        if artwork.image:
            try:
                artwork.image.storage.delete(artwork.image.name)
            except Exception:
                logger.exception("Could not delete an uploaded application image.")
                messages.error(
                    request,
                    "The application was not deleted because an uploaded image could not be removed. Please retry or contact support.",
                )
                return redirect("gallery_signups:application_detail", application_id=application.pk)
    application.delete()
    messages.success(request, "The application and its uploaded images were deleted.")
    return redirect("gallery_signups:application_list")


@require_POST
def approve_application(request, application_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    application = get_object_or_404(GalleryArtistApplication, pk=application_id, status="pending")
    form = ApplicationDecisionForm(request.POST, application=application)
    if not form.is_valid():
        messages.error(request, "Choose one of the applicant's requested months.")
        return redirect("gallery_signups:application_detail", application_id=application.pk)

    selected_event_id = form.cleaned_data["selected_event"].pk
    with transaction.atomic():
        application = get_object_or_404(
            GalleryArtistApplication.objects.select_for_update(), pk=application_id, status="pending"
        )
        event = get_object_or_404(
            FeaturedArtistEvent.objects.select_for_update(), pk=selected_event_id
        )
        slots = list(
            FeaturedArtistSlot.objects.select_for_update()
            .filter(event=event, slot_type="artist", artist_name="", reservation_label="")
            .order_by("position")
        )
        if event.is_closed or len(slots) < application.wall_count:
            messages.error(request, "That month no longer has enough open walls. Choose another requested month.")
            return redirect("gallery_signups:application_detail", application_id=application.pk)
        for slot in slots[:application.wall_count]:
            previous = slot.artist_name
            slot.artist_name = application.artist_name
            slot.guest_application = application
            slot.save(update_fields=["artist_name", "guest_application", "updated_at"])
            GallerySignupChange.objects.create(
                event_date=event.event_date, slot_label=slot.slot_label,
                action="guest_approved", old_name=previous,
                new_name=application.artist_name,
            )
        application.status = "approved"
        application.selected_event = event
        application.admin_note = form.cleaned_data["admin_note"].strip()
        application.save(update_fields=["status", "selected_event", "admin_note", "updated_at"])

    email_sent = _send_application_email(
        "Your Images Art Gallery Featured Artist request was approved",
        f"Hello {application.artist_name},\n\nYour request for {event:%B %Y} has been approved for "
        f"{application.wall_count} wall(s). The gallery will coordinate contract signing and hanging details with you. "
        "Payment remains due when the artwork is hung, as stated in the existing contract.\n\nImages Art Gallery",
        application.email,
    )
    if email_sent:
        messages.success(request, f"Application approved for {event:%B %Y}; the artist was emailed.")
    else:
        messages.warning(request, f"Application approved for {event:%B %Y}, but the artist email was not sent. Please contact them directly.")
    return redirect("gallery_signups:application_detail", application_id=application.pk)


@require_POST
def decline_application(request, application_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    application = get_object_or_404(GalleryArtistApplication, pk=application_id, status="pending")
    application.status = "not_selected"
    application.admin_note = request.POST.get("admin_note", "").strip()
    application.save(update_fields=["status", "admin_note", "updated_at"])
    email_sent = _send_application_email(
        "Update on your Images Art Gallery Featured Artist request",
        f"Hello {application.artist_name},\n\nThank you for your interest. We are unable to offer a wall "
        "from the months requested at this time. Please contact the gallery if you would like to be considered again.\n\n"
        "Images Art Gallery",
        application.email,
    )
    if email_sent:
        messages.success(request, "Application marked not selected; the artist was emailed.")
    else:
        messages.warning(request, "Application marked not selected, but the email was not sent. Please contact the artist directly.")
    return redirect("gallery_signups:application_detail", application_id=application.pk)


def admin_login(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if next_url and not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    form = AdminLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip()
        password = form.cleaned_data["password"]
        user = authenticate(request, username=username, password=password)
        if user and user.is_active and user.is_superuser:
            request.session.flush()
            login(request, user)
            return redirect(next_url or reverse("gallery_signups:manage"))
        account = GalleryAdministrator.objects.filter(username__iexact=username, is_active=True).first()
        if account and account.check_password(password):
            logout(request)
            request.session.flush()
            request.session["gallery_admin_id"] = account.pk
            request.session.set_expiry(60 * 60 * 12)
            return redirect(next_url or reverse("gallery_signups:manage"))
        form.add_error(None, "The username or password was not recognized.")
    return render(request, "gallery_signups/admin_login.html", {"form": form, "next": next_url})


def admin_logout(request):
    logout(request)
    request.session.flush()
    return redirect("gallery_signups:admin_login")


def manage(request):
    if not _admin_allowed(request):
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    events = FeaturedArtistEvent.objects.filter(year=2027).prefetch_related("slots")
    return render(request, "gallery_signups/manage.html", {
        "events": events,
        "is_owner": bool(request.user.is_authenticated and request.user.is_superuser),
        "pending_applications": GalleryArtistApplication.objects.filter(status="pending").count(),
    })


def signup_history(request):
    if not _admin_allowed(request):
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    changes = GallerySignupChange.objects.all()[:500]
    return render(request, "gallery_signups/signup_history.html", {"changes": changes})


@require_POST
def save_slot(request, slot_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    slot = get_object_or_404(FeaturedArtistSlot.objects.select_related("event"), pk=slot_id)
    old_name = slot.display_name
    if request.POST.get("action") == "clear":
        slot.artist_name = ""
        slot.reservation_label = ""
        slot.guest_application = None
        slot.save(update_fields=["artist_name", "reservation_label", "guest_application", "updated_at"])
        if old_name:
            _record_change(slot, "admin_clear", old_name=old_name)
    else:
        form = SlotEditForm(request.POST)
        if form.is_valid():
            artist = form.cleaned_data["artist_name"].strip()
            reserved = form.cleaned_data["reservation_label"].strip()
            if not (artist and reserved):
                slot.artist_name, slot.reservation_label = artist, reserved
                slot.guest_application = None
                slot.save(update_fields=["artist_name", "reservation_label", "guest_application", "updated_at"])
                new_name = slot.display_name
                if old_name != new_name:
                    _record_change(slot, "admin_edit", old_name=old_name, new_name=new_name)
    return redirect("gallery_signups:manage")


@require_POST
def save_event(request, event_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    event = get_object_or_404(FeaturedArtistEvent, pk=event_id)
    form = EventEditForm(request.POST)
    if form.is_valid():
        event.title = form.cleaned_data["title"].strip()
        event.is_closed = form.cleaned_data["is_closed"]
        event.save(update_fields=["title", "is_closed"])
    return redirect("gallery_signups:manage")


def owner_settings(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    form = MemberSettingsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        settings_row = GallerySettings.current()
        settings_row.set_member_password(form.cleaned_data["member_password"])
        settings_row.save()
        return render(request, "gallery_signups/settings.html", {"form": MemberSettingsForm(), "saved": True})
    return render(request, "gallery_signups/settings.html", {"form": form})


def owner_administrators(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect_to_login(request.get_full_path(), login_url=reverse("gallery_signups:admin_login"))
    form, message = AdministratorForm(), ""
    if request.method == "POST":
        action = request.POST.get("action")
        account = get_object_or_404(GalleryAdministrator, pk=request.POST.get("account_id")) if action in {"reset", "deactivate", "reactivate"} else None
        if action == "add":
            form = AdministratorForm(request.POST)
            if form.is_valid():
                username = form.cleaned_data["username"].strip()
                if GalleryAdministrator.objects.filter(username__iexact=username).exists():
                    form.add_error("username", "That username is already in use.")
                else:
                    account = GalleryAdministrator(username=username)
                    account.set_password(form.cleaned_data["password"])
                    account.save()
                    message = "Administrator added."
        elif action == "reset" and account:
            password = request.POST.get("new_password", "")
            if len(password) >= 12:
                account.set_password(password)
                account.save(update_fields=["password_hash"])
                message = "Administrator password reset."
        elif action in {"deactivate", "reactivate"} and account:
            account.is_active = action == "reactivate"
            account.save(update_fields=["is_active"])
            message = "Administrator access updated."
    return render(request, "gallery_signups/administrators.html", {
        "form": form, "accounts": GalleryAdministrator.objects.all(), "message": message,
    })
