"""Accounting-only URL configuration for development CI tests."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounting/", include("accounting.urls")),
]
