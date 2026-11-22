"""URL configuration for automation, inventory, and gallery sign-ups."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.index_template = "admin/backoffice_index.html"

urlpatterns = [
    path("", RedirectView.as_view(url="/automation/", permanent=False)),
    path("admin/", admin.site.urls),
    path("automation/", include("web_automation.urls")),
    path("inventory/", include("art_inventory.urls")),
    path("gallery-signups/", include("gallery_signups.urls")),
]
