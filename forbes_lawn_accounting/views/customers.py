# forbes_lawn_accounting/views/customers.py
"""
Customer Views - List and Detail
Shows customers synced from Jobber with search and filtering
"""

from django.views.generic import ListView, DetailView
from django.db.models import Q, Sum
from forbes_lawn_accounting.models import Customer, Invoice


class CustomerListView(ListView):
    model = Customer
    template_name = 'forbes_lawn_accounting/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = Customer.objects.all().order_by('name')
        
        # Get entity (assuming single Forbes Lawn entity)
        # Later can filter by entity if needed
        
        # Search functionality
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(service_address_line1__icontains=search) |
                Q(service_city__icontains=search) |
                Q(service_zip__icontains=search)
            )
        
        # Filter by active status
        status = self.request.GET.get('status', 'active')
        if status == 'active':
            queryset = queryset.filter(active=True)
        elif status == 'inactive':
            queryset = queryset.filter(active=False)
        # 'all' shows everything
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['status'] = self.request.GET.get('status', 'active')
        
        # Summary stats
        queryset = self.get_queryset()
        context['total_customers'] = queryset.count()
        
        return context


class CustomerDetailView(DetailView):
    model = Customer
    template_name = 'forbes_lawn_accounting/customer_detail.html'
    context_object_name = 'customer'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object
        
        # Get all invoices for this customer
        invoices = Invoice.objects.filter(customer=customer).order_by('-invoice_date')
        
        context['invoices'] = invoices
        context['invoice_count'] = invoices.count()
        
        # AR balance (unpaid invoices)
        context['ar_balance'] = customer.get_balance()
        
        # Total invoiced (all time)
        context['total_invoiced'] = invoices.aggregate(
            total=Sum('total')
        )['total'] or 0
        
        # Total paid
        context['total_paid'] = invoices.aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        return context
