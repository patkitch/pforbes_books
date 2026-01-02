# forbes_lawn_accounting/urls.py
"""
URLs for Forbes Lawn Accounting Dashboard
"""

from django.urls import path
from forbes_lawn_accounting.views.dashboard import DashboardView
from forbes_lawn_accounting.views.customers import CustomerListView, CustomerDetailView
from forbes_lawn_accounting.views.service_items import (
    ServiceItemListView, ServiceItemCreateView, ServiceItemUpdateView
)

app_name = 'forbes_lawn_accounting'

urlpatterns = [
    # Dashboard
    path('', DashboardView.as_view(), name='dashboard'),
    
    # Customers
    path('customers/', CustomerListView.as_view(), name='customer_list'),
    path('customers/<int:pk>/', CustomerDetailView.as_view(), name='customer_detail'),
    
    # Service Items
    path('service-items/', ServiceItemListView.as_view(), name='service_item_list'),
    path('service-items/add/', ServiceItemCreateView.as_view(), name='service_item_add'),
    path('service-items/<int:pk>/edit/', ServiceItemUpdateView.as_view(), name='service_item_edit'),
    
    # Invoices (placeholders - we'll create these views next)
    # path('invoices/', InvoiceListView.as_view(), name='invoice_list'),
    # path('invoices/unpaid/', InvoiceListView.as_view(queryset_filter='unpaid'), name='invoice_unpaid'),
    # path('invoices/<int:pk>/', InvoiceDetailView.as_view(), name='invoice_detail'),
    
    # Payments (placeholder)
    # path('payments/', PaymentListView.as_view(), name='payment_list'),
    
    # Reports (placeholders)
    # path('reports/sales-tax/', SalesTaxReportView.as_view(), name='sales_tax_report'),
    # path('reports/ar-aging/', ARAgingView.as_view(), name='ar_aging'),
    # path('reports/revenue-expenses/', RevenueExpensesView.as_view(), name='revenue_expenses'),
    # path('reports/balance-check/', BalanceCheckView.as_view(), name='balance_check'),
]