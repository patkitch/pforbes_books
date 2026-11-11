"""URL configuration for the remaining admin and product-automation site."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/automation/", permanent=False)),
    path("admin/", admin.site.urls),
    path("automation/", include("web_automation.urls")),
]
