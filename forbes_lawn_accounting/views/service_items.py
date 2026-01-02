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
    fields = ['name', 'description', 'category_name', 'default_rate', 'taxable', 'revenue_account', 'active']
    success_url = reverse_lazy('forbes_lawn_accounting:service_item_list')
    
    def get_form(self, form_class=None):
        """Filter revenue account dropdown to Forbes Lawn entity only"""
        form = super().get_form(form_class)
        
        # Get Forbes Lawn entity
        forbes_entity = EntityModel.objects.filter(
            name__icontains='Forbes Lawn Spraying'
        ).first()
        
        if forbes_entity:
            # Filter revenue accounts to this entity and revenue accounts (4024/4025)
            from django_ledger.models import AccountModel
            form.fields['revenue_account'].queryset = AccountModel.objects.filter(
                coa_model__entity=forbes_entity,
                code__in=['4024', '4025']
            ).order_by('code')
        
        return form
    
    def form_valid(self, form):
        # Auto-set Forbes Lawn entity
        forbes_entity = EntityModel.objects.filter(
            name__icontains='Forbes Lawn Spraying'
        ).first()
        
        if not forbes_entity:
            from django.contrib import messages
            messages.error(self.request, 'Forbes Lawn Spraying entity not found!')
            return self.form_invalid(form)
        
        form.instance.entity = forbes_entity
        
        # Generate unique jobber_id for manually created items
        import uuid
        form.instance.jobber_id = f"manual-{uuid.uuid4().hex[:12]}"
        
        # Set synced_at
        from django.utils import timezone
        form.instance.synced_at = timezone.now()
        
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
    fields = ['name', 'description', 'category_name', 'default_rate', 'taxable', 'revenue_account', 'active']
    success_url = reverse_lazy('forbes_lawn_accounting:service_item_list')
    
    def get_form(self, form_class=None):
        """Filter revenue account dropdown to Forbes Lawn entity only"""
        form = super().get_form(form_class)
        
        # Get Forbes Lawn entity
        forbes_entity = EntityModel.objects.filter(
            name__icontains='Forbes Lawn Spraying'
        ).first()
        
        if forbes_entity:
            # Filter revenue accounts to this entity and revenue accounts (4024/4025)
            from django_ledger.models import AccountModel
            form.fields['revenue_account'].queryset = AccountModel.objects.filter(
                coa_model__entity=forbes_entity,
                code__in=['4024', '4025']
            ).order_by('code')
        
        return form
    
    def form_valid(self, form):
        messages.success(self.request, f'Service item "{form.instance.name}" updated successfully!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit Service Item: {self.object.name}'
        context['submit_text'] = 'Save Changes'
        return context