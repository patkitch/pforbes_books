# forbes_lawn_dashboard/urls.py

from django.urls import path
from . import views

app_name = "forbes_lawn_dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
]
