"""Local accounting routes; production URL configuration stays unchanged."""
from django.urls import include, path
from django.views.generic import RedirectView
from .urls import urlpatterns as base_patterns

urlpatterns = [
    path("", RedirectView.as_view(url="/accounting/", permanent=False)),
    path("accounting/", include("accounting.urls")),
    *[pattern for pattern in base_patterns if str(pattern.pattern) not in ("", "accounting/")],
]
