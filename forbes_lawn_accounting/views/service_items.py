# forbes_lawn_accounting/views/service_items.py
"""
Service Item Views - List, Add, Edit
Manage services offered (lawn treatments, aeration, etc.)
"""

from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from forbes_lawn_accounting.models import ServiceItem
from django_ledger.models import EntityModel


class ServiceItemListView(ListView):
    model = ServiceItem
    template_name = 'forbes_lawn_accounting/service_item_list.html'
    context_object_name = 'service_items'
    
    def get_queryset(self):
        # Get entity (assuming Forbes Lawn entity)
        entity = EntityModel.objects.first()
        return ServiceItem.objects.filter(entity=entity).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        
        # Stats
        context['total_items'] = queryset.count()
        context['active_items'] = queryset.filter(active=True).count()
        context['taxable_items'] = queryset.filter(taxable=True).count()
        
        return context


class ServiceItemCreateView(CreateView):
    model = ServiceItem
    template_name = 'forbes_lawn_accounting/service_item_form.html'
    fields = ['name', 'description', 'category', 'default_rate', 'taxable', 'revenue_account', 'active']
    success_url = reverse_lazy('forbes_lawn_accounting:service_item_list')
    
    def form_valid(self, form):
        # Auto-set entity
        form.instance.entity = EntityModel.objects.first()
        messages.success(self.request, f'Service item "{form.instance.name}" created successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add New Service Item'
        context['submit_text'] = 'Create Service Item'
        return context


class ServiceItemUpdateView(UpdateView):
    model = ServiceItem
    template_name = 'forbes_lawn_accounting/service_item_form.html'
    fields = ['name', 'description', 'category', 'default_rate', 'taxable', 'revenue_account', 'active']
    success_url = reverse_lazy('forbes_lawn_accounting:service_item_list')
    
    def form_valid(self, form):
        messages.success(self.request, f'Service item "{form.instance.name}" updated successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit Service Item: {self.object.name}'
        context['submit_text'] = 'Save Changes'
        return context
