# reports/urls.py
from django.urls import path
from . import views

app_name = "reports"


urlpatterns = [
    path("health/", views.health_check, name="health"),
    path("downloads/<str:filename>/", download_report, name="download_report"),
]
