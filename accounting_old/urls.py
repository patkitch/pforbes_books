# accounting/urls.py
from django.urls import path
from .views import apply_payment_view

app_name = "accounting"

urlpatterns = [
    path("payments/apply/", apply_payment_view, name="apply_payment"),
]
