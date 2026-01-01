# forbes_lawn_accounting/views/dashboard.py
"""
Main Dashboard View - First thing users see
Shows today's snapshot, weekly revenue, monthly summary, and alerts
"""

from django.views.generic import TemplateView
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from forbes_lawn_accounting.models import (
    Invoice, 
    InvoicePayment, 
    Customer,
    SalesTaxSummary,
    InvoiceStatus
)


class DashboardView(TemplateView):
    template_name = 'forbes_lawn_accounting/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        month_start = today.replace(day=1)
        
        # Get entity (assuming single entity for now)
        from django_ledger.models import EntityModel
        entity = EntityModel.objects.first()
        
        # ============================================================
        # TODAY'S SNAPSHOT
        # ============================================================
        
        # Today's revenue
        context['today_revenue'] = Invoice.objects.filter(
            entity=entity,
            invoice_date=today
        ).exclude(
            status=InvoiceStatus.VOID
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Unpaid invoices
        unpaid = Invoice.objects.filter(
            entity=entity,
            balance_due__gt=0
        ).exclude(
            status__in=[InvoiceStatus.VOID, InvoiceStatus.PAID]
        ).aggregate(
            count=Count('id'),
            total=Sum('balance_due')
        )
        
        context['unpaid_invoices'] = {
            'count': unpaid['count'] or 0,
            'total': unpaid['total'] or Decimal('0.00')
        }
        
        # Cash balance (placeholder - will come from Django-Ledger later)
        context['cash_balance'] = Decimal('0.00')  # TODO: Get from ledger
        
        # ============================================================
        # THIS WEEK
        # ============================================================
        
        week_revenue = Invoice.objects.filter(
            entity=entity,
            invoice_date__gte=week_start,
            invoice_date__lte=today
        ).exclude(
            status=InvoiceStatus.VOID
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Last week for comparison
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start - timedelta(days=1)
        
        last_week_revenue = Invoice.objects.filter(
            entity=entity,
            invoice_date__gte=last_week_start,
            invoice_date__lte=last_week_end
        ).exclude(
            status=InvoiceStatus.VOID
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Calculate percent change
        if last_week_revenue > 0:
            week_change = ((week_revenue - last_week_revenue) / last_week_revenue * 100)
        else:
            week_change = 0 if week_revenue == 0 else 100
        
        context['week_revenue'] = week_revenue
        context['week_change'] = round(week_change, 1)
        
        # ============================================================
        # THIS MONTH
        # ============================================================
        
        context['month_revenue'] = Invoice.objects.filter(
            entity=entity,
            invoice_date__gte=month_start
        ).exclude(
            status=InvoiceStatus.VOID
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        # Monthly expenses (placeholder - from Django-Ledger)
        context['month_expenses'] = Decimal('0.00')  # TODO: Get from ledger
        
        # Net income
        context['month_net'] = context['month_revenue'] - context['month_expenses']
        
        # Sales tax for the month
        context['month_tax'] = Invoice.objects.filter(
            entity=entity,
            invoice_date__gte=month_start
        ).exclude(
            status=InvoiceStatus.VOID
        ).aggregate(total=Sum('tax_amount'))['total'] or Decimal('0.00')
        
        # ============================================================
        # ALERTS / NEEDS ATTENTION
        # ============================================================
        
        alerts = []
        
        # Unpaid invoices
        if context['unpaid_invoices']['count'] > 0:
            alerts.append({
                'type': 'warning',
                'icon': '💰',
                'message': f"{context['unpaid_invoices']['count']} unpaid invoices (${context['unpaid_invoices']['total']:,.2f})",
                'link': '/invoices/unpaid/',
                'link_text': 'View Unpaid Invoices'
            })
        
        # Sales tax due soon
        try:
            current_month = month_start
            tax_summary, created = SalesTaxSummary.objects.get_or_create(
                entity=entity,
                month=current_month,
                defaults={
                    'total_revenue': Decimal('0.00'),
                    'tax_collected': Decimal('0.00')
                }
            )
            
            if not tax_summary.filed and tax_summary.is_due_soon:
                alerts.append({
                    'type': 'danger',
                    'icon': '⚠️',
                    'message': f"Sales tax due in {tax_summary.days_until_due} days (${tax_summary.tax_collected:,.2f})",
                    'link': '/reports/sales-tax/',
                    'link_text': 'File Sales Tax'
                })
            elif not tax_summary.filed and tax_summary.is_overdue:
                alerts.append({
                    'type': 'danger',
                    'icon': '🚨',
                    'message': f"Sales tax OVERDUE by {abs(tax_summary.days_until_due)} days!",
                    'link': '/reports/sales-tax/',
                    'link_text': 'File Now'
                })
        except Exception as e:
            # Don't break dashboard if tax summary fails
            pass
        
        # Overdue invoices
        overdue_count = Invoice.objects.filter(
            entity=entity,
            balance_due__gt=0,
            due_date__lt=today
        ).exclude(
            status__in=[InvoiceStatus.VOID, InvoiceStatus.PAID]
        ).count()
        
        if overdue_count > 0:
            alerts.append({
                'type': 'warning',
                'icon': '📅',
                'message': f"{overdue_count} invoices are overdue",
                'link': '/invoices/overdue/',
                'link_text': 'View Overdue'
            })
        
        context['alerts'] = alerts
        
        # ============================================================
        # QUICK STATS
        # ============================================================
        
        context['stats'] = {
            'total_customers': Customer.objects.filter(entity=entity, active=True).count(),
            'invoices_this_month': Invoice.objects.filter(
                entity=entity,
                invoice_date__gte=month_start
            ).exclude(status=InvoiceStatus.VOID).count(),
            'payments_this_week': InvoicePayment.objects.filter(
                invoice__entity=entity,
                payment_date__gte=week_start
            ).count(),
        }
        
        # Current month name
        context['current_month'] = today.strftime('%B %Y')
        
        return context
