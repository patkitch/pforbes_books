# forbes_lawn_accounting/views/sales_tax.py
"""
Sales Tax Report Views
Monthly sales tax tracking and filing status
"""

from django.views.generic import TemplateView
from django.http import HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
import csv

from forbes_lawn_accounting.models import Invoice, SalesTaxSummary
from django_ledger.models import EntityModel


class SalesTaxReportView(TemplateView):
    template_name = 'forbes_lawn_accounting/sales_tax_report.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get selected month (default to current month)
        month_str = self.request.GET.get('month')
        if month_str:
            try:
                selected_date = datetime.strptime(month_str, '%Y-%m')
            except:
                selected_date = timezone.now()
        else:
            selected_date = timezone.now()
        
        # Get Forbes Lawn entity
        # Get Forbes Lawn entity by slug (production)
        entity = EntityModel.objects.get(slug='forbes-lawn-spraying-llc-elg3zg1u')
        
        # Calculate month boundaries
        first_day = selected_date.replace(day=1)
        if first_day.month == 12:
            last_day = first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)
        
        # Get invoices for the month
        invoices = Invoice.objects.filter(
            entity=entity,
            invoice_date__gte=first_day,
            invoice_date__lte=last_day
        ).exclude(status='VOID')
        
        # Calculate totals
        total_revenue = invoices.aggregate(Sum('total'))['total__sum'] or 0
        total_taxable = invoices.aggregate(Sum('taxable_subtotal'))['taxable_subtotal__sum'] or 0
        total_tax = invoices.aggregate(Sum('tax_amount'))['tax_amount__sum'] or 0
        
        # Parse tax by jurisdiction
        jurisdictions = self.parse_tax_by_jurisdiction(invoices)
        
        # Get or create tax summary
        tax_summary, created = SalesTaxSummary.objects.get_or_create(
            entity=entity,
            month=first_day,
            defaults={
                'total_revenue': total_revenue,
                'taxable_revenue': total_taxable,
                'non_taxable_revenue': total_revenue - total_taxable,
                'tax_collected': total_tax,
            }
        )
        
        # Calculate due date (20th of following month)
        due_date = (last_day + timedelta(days=1)).replace(day=20)
        days_until_due = (due_date.date() - timezone.now().date()).days
        
        # Context
        context.update({
            'selected_month': first_day,
            'month_display': first_day.strftime('%B %Y'),
            'month_value': first_day.strftime('%Y-%m'),
            'total_revenue': total_revenue,
            'total_taxable': total_taxable,
            'total_tax': total_tax,
            'jurisdictions': jurisdictions,
            'tax_summary': tax_summary,
            'due_date': due_date,
            'days_until_due': days_until_due,
            'is_overdue': days_until_due < 0 and not tax_summary.filed_date,
            'is_due_soon': 0 <= days_until_due <= 10 and not tax_summary.filed_date,
            'available_months': self.get_available_months(),
        })
        
        return context
    
    def parse_tax_by_jurisdiction(self, invoices):
        """
        Parse tax amounts by jurisdiction (State, County, City)
        Based on tax_rate_name field in invoices
        """
        jurisdictions = {}
        
        # Standard Kansas tax rates
        state_rate = 6.5
        county_rate = 1.475  # Johnson County
        
        # City rates (from property data)
        city_rates = {
            'Mission': 1.75,
            'Olathe': 1.5,
            'Overland Park': 1.375,
            'Prairie Village': 1.0,
            'Westwood': 1.5,
            'Lenexa': 1.35,
        }
        
        # Calculate taxable amount (sum of taxable line items)
        taxable_total = 0
        city_breakdowns = {}
        
        for invoice in invoices:
            if invoice.tax_amount and invoice.tax_amount > 0:
                taxable_total += float(invoice.taxable_subtotal or 0)
                
                # Parse city from property
                if invoice.property:
                    city = invoice.property.city
                    if city not in city_breakdowns:
                        city_breakdowns[city] = 0
                    city_breakdowns[city] += float(invoice.taxable_subtotal or 0)
        
        # Build jurisdiction summary (like Jobber format)
        result = []
        
        # State
        result.append({
            'name': f'Kansas State ({state_rate}%)',
            'taxable': taxable_total,
            'tax': taxable_total * (state_rate / 100),
            'level': 'state'
        })
        
        # County (if any taxable revenue in Kansas)
        if taxable_total > 0:
            result.append({
                'name': f'Kansas, Johnson County ({county_rate}%)',
                'taxable': taxable_total,
                'tax': taxable_total * (county_rate / 100),
                'level': 'county'
            })
        
        # Cities
        for city, amount in city_breakdowns.items():
            city_rate = city_rates.get(city, 1.0)  # Default 1% if city not found
            result.append({
                'name': f'Kansas, {city} City ({city_rate}%)',
                'taxable': amount,
                'tax': amount * (city_rate / 100),
                'level': 'city'
            })
        
        return result
    
    def get_available_months(self):
        """Get list of available months (Jan 2026 forward)"""
        months = []
        start = datetime(2026, 1, 1)
        current = timezone.now().replace(tzinfo=None)
        
        month = start
        while month <= current:
            months.append({
                'value': month.strftime('%Y-%m'),
                'display': month.strftime('%B %Y')
            })
            # Next month
            if month.month == 12:
                month = month.replace(year=month.year + 1, month=1)
            else:
                month = month.replace(month=month.month + 1)
        
        return months


class SalesTaxDownloadCSVView(TemplateView):
    """Download sales tax report as CSV (Jobber format)"""
    
    def get(self, request, *args, **kwargs):
        month_str = request.GET.get('month')
        if not month_str:
            month_str = timezone.now().strftime('%Y-%m')
        
        selected_date = datetime.strptime(month_str, '%Y-%m')
        
        # Get data (reuse logic from report view)
        report_view = SalesTaxReportView()
        report_view.request = request
        context = report_view.get_context_data()
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        filename = f"Sales_Tax_Report_{selected_date.strftime('%b_%Y')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow(['Tax Report'])
        writer.writerow(['ACCRUAL REPORT'])
        writer.writerow(['Total', f"${context['total_tax']:.2f}"])
        writer.writerow(['Bad Debt', '$0.00'])
        writer.writerow([])
        
        # Jurisdiction breakdown
        writer.writerow(['Tax Name', 'Taxable', 'Tax', 'Bad Debt Taxable', 'Bad Debt Tax'])
        
        for jurisdiction in context['jurisdictions']:
            writer.writerow([
                jurisdiction['name'],
                f"${jurisdiction['taxable']:.2f}",
                f"${jurisdiction['tax']:.2f}",
                '$0.00',
                '$0.00'
            ])
        
        writer.writerow(['Non-Taxable Total', '$0.00', '-', '$0.00', '-'])
        
        return response