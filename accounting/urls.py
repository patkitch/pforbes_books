from django.urls import path
from . import views

app_name = "accounting"
urlpatterns = [
    path("accounts/", views.chart_of_accounts, name="chart_of_accounts"),
]
