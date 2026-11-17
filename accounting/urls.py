from django.urls import path
from accounting_contacts import views as contact_views
from . import views, split_views, report_views, report_exports, owner_views, money_views, correction_views, journal_views, trial_views

app_name = "accounting"
urlpatterns = [
    path("reports/trial-balance/", trial_views.trial_balance_view, name="trial_balance"),
    path("reports/trial-balance.csv", trial_views.trial_balance_csv, name="trial_balance_csv"),
    path("transactions/journal/new/", journal_views.journal_new, name="journal_new"),
    path("transactions/journal/<int:pk>/edit/", journal_views.journal_edit, name="journal_edit"),
    path("transactions/movement/new/", money_views.movement_new, name="movement_new"),
    path("transactions/movement/<int:pk>/edit/", money_views.movement_edit, name="movement_edit"),
    path("transactions/<int:pk>/reverse/", correction_views.reverse_transaction, name="transaction_reverse"),
    path("transactions/owner/new/", owner_views.owner_new, name="owner_new"),
    path("transactions/owner/<int:pk>/edit/", owner_views.owner_edit, name="owner_edit"),
    path("reports/download/<str:kind>/<str:format>/", report_exports.report_download, name="report_download"),
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
