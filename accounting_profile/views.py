from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from .forms import BusinessProfileForm
from .models import BusinessProfile


@never_cache
@staff_member_required(login_url="/admin/login/")
def business_profile(request):
    # v1 single-company accounting ledger; do not imply multi-tenant support.
    profile = BusinessProfile.objects.order_by("pk").first()
    if request.method == "POST":
        form = BusinessProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("accounting:business_profile")
    else:
        form = BusinessProfileForm(instance=profile, initial={
            "display_name": "P. Forbes Art",
        } if profile is None else None)
    return render(request, "accounting_profile/business_profile.html", {
        "profile": profile, "form": form,
    })
