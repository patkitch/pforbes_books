from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AdminLoginForm, AdministratorForm, ClaimSlotForm, EventEditForm, MemberPasswordForm, MemberSettingsForm, SlotEditForm
from .models import FeaturedArtistEvent, FeaturedArtistSlot, GalleryAdministrator, GallerySettings

def _member_allowed(request):
    return request.session.get("gallery_member_access") is True

def _admin_account(request):
    key = request.session.get("gallery_admin_id")
    return GalleryAdministrator.objects.filter(pk=key, is_active=True).first() if key else None

def _admin_allowed(request):
    return (request.user.is_authenticated and request.user.is_superuser) or _admin_account(request) is not None

def member_login(request):
    settings = GallerySettings.current()
    form = MemberPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if settings.check_member_password(form.cleaned_data["password"]):
            logout(request)
            request.session.flush()
            request.session["gallery_member_access"] = True
            request.session.set_expiry(60 * 60 * 24 * 14)
            return redirect("gallery_signups:calendar")
        form.add_error("password", "That password did not match. Please check with Patricia.")
    return render(request, "gallery_signups/member_login.html", {"form": form, "configured": bool(settings.member_password_hash)})

def member_logout(request):
    request.session.pop("gallery_member_access", None)
    return redirect("gallery_signups:member_login")

def calendar(request, year=2027):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    events = FeaturedArtistEvent.objects.filter(year=year).prefetch_related("slots")
    return render(request, "gallery_signups/calendar.html", {"events": events, "year": year})

@require_POST
def claim_slot(request, slot_id):
    if not _member_allowed(request):
        return redirect("gallery_signups:member_login")
    form = ClaimSlotForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            slot = get_object_or_404(FeaturedArtistSlot.objects.select_for_update().select_related("event"), pk=slot_id)
            if slot.is_open:
                slot.artist_name = form.cleaned_data["name"]
                slot.save(update_fields=["artist_name", "updated_at"])
    return redirect("gallery_signups:calendar")

def admin_login(request):
    form = AdminLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip()
        password = form.cleaned_data["password"]
        user = authenticate(request, username=username, password=password)
        if user and user.is_active and user.is_superuser:
            request.session.flush()
            login(request, user)
            return redirect("gallery_signups:manage")
        account = GalleryAdministrator.objects.filter(username__iexact=username, is_active=True).first()
        if account and account.check_password(password):
            logout(request)
            request.session.flush()
            request.session["gallery_admin_id"] = account.pk
            request.session.set_expiry(60 * 60 * 12)
            return redirect("gallery_signups:manage")
        form.add_error(None, "The username or password was not recognized.")
    return render(request, "gallery_signups/admin_login.html", {"form": form})

def admin_logout(request):
    logout(request)
    request.session.flush()
    return redirect("gallery_signups:admin_login")

def manage(request):
    if not _admin_allowed(request):
        return redirect("gallery_signups:admin_login")
    events = FeaturedArtistEvent.objects.filter(year=2027).prefetch_related("slots")
    return render(request, "gallery_signups/manage.html", {
        "events": events,
        "is_owner": bool(request.user.is_authenticated and request.user.is_superuser),
    })

@require_POST
def save_slot(request, slot_id):
    if not _admin_allowed(request):
        return HttpResponseForbidden()
    slot = get_object_or_404(FeaturedArtistSlot.objects.select_related("event"), pk=slot_id)
    if request.POST.get("action") == "clear":
        slot.artist_name = ""
        slot.reservation_label = ""
        slot.save(update_fields=["artist_name", "reservation_label", "updated_at"])
    else:
        form = SlotEditForm(request.POST)
        if form.is_valid():
            artist = form.cleaned_data["artist_name"].strip()
            reserved = form.cleaned_data["reservation_label"].strip()
            if not (artist and reserved):
                slot.artist_name, slot.reservation_label = artist, reserved
                slot.save(update_fields=["artist_name", "reservation_label", "updated_at"])
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
        return redirect("gallery_signups:admin_login")
    form = MemberSettingsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        settings = GallerySettings.current()
        settings.set_member_password(form.cleaned_data["member_password"])
        settings.save()
        return render(request, "gallery_signups/settings.html", {"form": MemberSettingsForm(), "saved": True})
    return render(request, "gallery_signups/settings.html", {"form": form})

def owner_administrators(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect("gallery_signups:admin_login")
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
