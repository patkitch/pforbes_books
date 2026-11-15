from django.urls import path
from . import views, split_views, report_views

app_name = "accounting"
urlpatterns = [
    path("reports/profit-loss/", report_views.profit_loss_view, name="profit_loss"),
    path("reports/balance-sheet/", report_views.balance_sheet_view, name="balance_sheet"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/split/new/", split_views.split_new, name="split_new"),
    path("transactions/split/<int:pk>/edit/", split_views.split_edit, name="split_edit"),
    path("transactions/new/", views.transaction_new, name="transaction_new"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("accounts/", views.chart_of_accounts, name="chart_of_accounts"),
    path("accounts/new/", views.account_form, name="account_new"),
    path("accounts/<int:pk>/ledger/", views.account_ledger, name="account_ledger"),
    path("accounts/<int:pk>/edit/", views.account_form, name="account_edit"),
    path("accounts/<int:pk>/status/", views.account_status, name="account_status"),
]
