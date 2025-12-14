# forbes_lawn_dashboard/urls.py

from django.urls import path
from . import views

app_name = "forbes_lawn_dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("tax/", views.tax_hub, name="tax_hub"),
    path("imports/", views.imports_hub, name="imports_hub"),
    path("accounting/", views.accounting_hub, name="accounting_hub"),

    # command endpoints
    path("imports/run-posting/", views.run_posting_command, name="run_posting_command"),
    path("imports/run-jobber-invoices/", views.run_jobber_invoices_command, name="run_jobber_invoices_command"),
    path("imports/run-jobber-payments/", views.run_jobber_payments_command, name="run_jobber_payments_command"),
]
