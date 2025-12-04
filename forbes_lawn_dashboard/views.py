# forbes_lawn_dashboard/views.py

from datetime import date
from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

# TODO: Once your custom invoice app exists, import it here.
# from forbes_lawn_billing.models import Invoice


def dashboard_home(request):
    """
    Forbes Lawn Home Dashboard (v1)
    - Shows stubbed metrics for now
    - Ready to plug into your custom Invoice model later
    """

    today = timezone.localdate()
    start_of_month = today.replace(day=1)

    # ========= STUB METRICS (replace later with real queries) =========
    open_invoices_total = Decimal("0.00")
    overdue_invoices_total = Decimal("0.00")
    overdue_invoices_count = 0
    payments_this_month_total = Decimal("0.00")

    next_sales_tax_due_date = None
    next_sales_tax_estimate = Decimal("0.00")

    open_invoices = []  # Placeholder list; will become a queryset later

    # ======= EXAMPLE LOGIC FOR LATER (when Invoice exists) =======
    # Uncomment and adapt to your custom Invoice model fields.
    #
    # from django.db.models import Sum, Q, F
    #
    # invoices_qs = Invoice.objects.all()
    #
    # open_invoices_qs = invoices_qs.filter(status="OPEN")
    # open_invoices_total = open_invoices_qs.aggregate(
    #     total=Sum("balance_due")
    # )["total"] or Decimal("0.00")
    #
    # overdue_invoices_qs = open_invoices_qs.filter(due_date__lt=today)
    # overdue_agg = overdue_invoices_qs.aggregate(
    #     total=Sum("balance_due")
    # )
    # overdue_invoices_total = overdue_agg["total"] or Decimal("0.00")
    # overdue_invoices_count = overdue_invoices_qs.count()
    #
    # payments_this_month_total = (
    #     invoices_qs.filter(
    #         paid_date__gte=start_of_month,
    #         paid_date__lte=today,
    #     ).aggregate(total=Sum("amount_paid"))["total"]
    #     or Decimal("0.00")
    # )
    #
    # open_invoices = (
    #     open_invoices_qs
    #     .select_related("customer")
    #     .order_by("due_date")[:10]
    # )

    context = {
        "today": today,
        "open_invoices_total": open_invoices_total,
        "overdue_invoices_total": overdue_invoices_total,
        "overdue_invoices_count": overdue_invoices_count,
        "payments_this_month_total": payments_this_month_total,
        "next_sales_tax_due_date": next_sales_tax_due_date,
        "next_sales_tax_estimate": next_sales_tax_estimate,
        "open_invoices": open_invoices,
    }

    return render(request, "forbes_lawn_dashboard/home.html", context)

