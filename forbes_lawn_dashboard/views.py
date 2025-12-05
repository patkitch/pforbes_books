# forbes_lawn_dashboard/views.py

from datetime import date
from decimal import Decimal
from django.db.models import Sum               # <-- ADD THIS
from django.shortcuts import render
from django.utils import timezone
from forbes_lawn_billing.models import Invoice, InvoicePayment, InvoiceStatus
from django_ledger.models.entity import EntityModel  # same caveat: adjust path if needed
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

ENTITY_NAME_FORBES_LAWN = "Forbes Lawn Spraying LLC"

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

    # Try to get the Forbes Lawn entity by NAME (works for both local & DO)
    try:
        entity = EntityModel.objects.get(name=ENTITY_NAME_FORBES_LAWN)
    except EntityModel.DoesNotExist:
        # If the entity isn't created in this environment yet, show an empty dashboard
        invoices_qs = Invoice.objects.none()
    else:
        invoices_qs = Invoice.objects.filter(entity=entity)
    # ========= STUB METRICS (replace later with real queries) =========
    open_invoices_total = Decimal("0.00")
    overdue_invoices_total = Decimal("0.00")
    overdue_invoices_count = 0
    payments_this_month_total = Decimal("0.00")

    next_sales_tax_due_date = None
    next_sales_tax_estimate = Decimal("0.00")

    # Placeholder list; will become a queryset later

    # ======= EXAMPLE LOGIC FOR LATER (when Invoice exists) =======
    # Uncomment and adapt to your custom Invoice model fields.
    #
    # from django.db.models import Sum, Q, F
    #
    open_invoices_qs = invoices_qs.filter(
        status__in=[InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID]
    )

    open_invoices_total = (
        open_invoices_qs.aggregate(total=Sum("balance_due"))["total"]
        or Decimal("0.00")
    )
    
    overdue_invoices_qs = open_invoices_qs.filter(due_date__lt=today)
    overdue_agg = overdue_invoices_qs.aggregate(total=Sum("balance_due"))
    overdue_invoices_total = overdue_agg["total"] or Decimal("0.00")
    overdue_invoices_count = overdue_invoices_qs.count()
    
    payments_this_month_total = (
        InvoicePayment.objects.filter(
            date__gte=start_of_month,
            date__lte=today,
            invoice__in=invoices_qs,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    # Still stub for now; we'll back this with tax tables later
    next_sales_tax_due_date = None
    next_sales_tax_estimate = Decimal("0.00")
    #
    open_invoices = (
        open_invoices_qs
        .order_by("due_date", "invoice_date", "id")[:10]
    )

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


def invoice_list(request):
    """
    Customer-facing table of all Forbes Lawn invoices.
    Supports basic filters: status & search.
    """
    try:
        entity = EntityModel.objects.get(name=ENTITY_NAME_FORBES_LAWN)
    except EntityModel.DoesNotExist:
        entity = None

    qs = Invoice.objects.none()
    if entity is not None:
        qs = Invoice.objects.filter(entity=entity).order_by("-invoice_date", "-id")

    # Filters
    status = request.GET.get("status") or ""
    search = request.GET.get("q") or ""

    if status:
        qs = qs.filter(status=status)

    if search:
        qs = qs.filter(
            # simple search on invoice number or customer name
            # (you can refine later)
            invoice_number__icontains=search
        ) | qs.filter(customer_name__icontains=search)

    # Pagination
    page = request.GET.get("page", 1)
    paginator = Paginator(qs, 25)  # 25 invoices per page

    try:
        invoices_page = paginator.page(page)
    except PageNotAnInteger:
        invoices_page = paginator.page(1)
    except EmptyPage:
        invoices_page = paginator.page(paginator.num_pages)

    context = {
        "entity": entity,
        "invoices_page": invoices_page,
        "status_filter": status,
        "search_query": search,
    }
    return render(request, "forbes_lawn_dashboard/invoice_list.html", context)