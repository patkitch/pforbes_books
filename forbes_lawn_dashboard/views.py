# forbes_lawn_dashboard/views.py

from datetime import date
from decimal import Decimal
from django.db.models import Sum               # <-- ADD THIS
from django.shortcuts import render
from django.utils import timezone
from forbes_lawn_billing.models import Invoice, InvoicePayment, InvoiceStatus
from django_ledger.models.entity import EntityModel  # same caveat: adjust path if needed
from django_ledger.models import StagedTransactionModel
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Sum, Q
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from io import StringIO
from django.shortcuts import redirect
from django.contrib import messages
from pathlib import Path

ENTITY_NAME_FORBES_LAWN = "Forbes Lawn Spraying LLC"

# TODO: Once your custom invoice app exists, import it here.
# from forbes_lawn_billing.models import Invoice

@staff_member_required
def run_posting_command(request):
    if request.method != "POST":
        return redirect("forbes_lawn_dashboard:imports_hub")

    entity_slug = request.POST.get("entity_slug", "").strip()
    ledger_xid = request.POST.get("ledger_xid", "").strip()
    year = int(request.POST.get("year", "2025"))

    out = StringIO()
    try:
        call_command(
            "post_forbes_lawn_2025_invoices",
            entity_slug=entity_slug,
            ledger_xid=ledger_xid,
            year=year,
            stdout=out,
            stderr=out,
        )
        messages.success(request, "Posting command ran successfully.")
    except Exception as e:
        messages.error(request, f"Posting command failed: {e}")

    request.session["imports_last_output"] = out.getvalue()
    return redirect("forbes_lawn_dashboard:imports_hub")
@staff_member_required
def run_jobber_invoices_command(request):
    if request.method != "POST":
        return redirect("forbes_lawn_dashboard:imports_hub")

    csv_path = request.POST.get("csv_path", "").strip()
    dry_run = request.POST.get("dry_run") == "1"

    out = StringIO()
    try:
        if dry_run:
            call_command("import_jobber_invoices", csv_path, "--dry-run", stdout=out, stderr=out)
        else:
            call_command("import_jobber_invoices", csv_path, stdout=out, stderr=out)

        messages.success(request, "Jobber invoices import ran successfully.")
    except Exception as e:
        messages.error(request, f"Jobber invoices import failed: {e}")

    request.session["imports_last_output"] = out.getvalue()
    return redirect("forbes_lawn_dashboard:imports_hub")

@staff_member_required
def run_jobber_payments_command(request):
    if request.method != "POST":
        return redirect("forbes_lawn_dashboard:imports_hub")

    csv_path = request.POST.get("csv_path", "").strip()
    dry_run = request.POST.get("dry_run") == "1"

    out = StringIO()
    try:
        if dry_run:
            call_command("import_jobber_payments", csv_path, "--dry-run", stdout=out, stderr=out)
        else:
            call_command("import_jobber_payments", csv_path, stdout=out, stderr=out)

        messages.success(request, "Jobber payments import ran successfully.")
    except Exception as e:
        messages.error(request, f"Jobber payments import failed: {e}")

    request.session["imports_last_output"] = out.getvalue()
    return redirect("forbes_lawn_dashboard:imports_hub")

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
            invoice__entity=entity,
            payment_date__gte=start_of_month,
            payment_date__lte=today,
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
        "Today": timezone.localdate(),
        "entity": entity,
        "invoices_page": invoices_page,
        "status_filter": status,
        "search_query": search,
    }
    return render(request, "forbes_lawn_dashboard/invoice_list.html", context)


def tax_hub(request):
    return render(request, "forbes_lawn_dashboard/tax_hub.html", {"today": timezone.localdate()})

def imports_hub(request):
    today = timezone.localdate()
    year = int(request.GET.get("year") or today.year)

    # Try to get Forbes Lawn entity by NAME (works across local & DO)
    try:
        entity = EntityModel.objects.get(name=ENTITY_NAME_FORBES_LAWN)
    except EntityModel.DoesNotExist:
        entity = None

    # Base context (define FIRST)
    context = {
        "today": today,
        "year": year,
        "invoices_unposted_count": 0,
        "invoices_unposted_total": Decimal("0.00"),
        "payments_unposted_count": 0,
        "payments_unposted_total": Decimal("0.00"),
        "bank_staged_count": 0,
        "bank_staged_total": Decimal("0.00"),
        "last_output": request.session.pop("imports_last_output", ""),
        "entity": entity,
    }

    if entity is None:
        return render(request, "forbes_lawn_dashboard/imports_hub.html", context)

    # -------------------------
    # POST: run commands
    # -------------------------
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        # helper to validate file paths from the dashboard
        def _validated_csv_path(field_name: str) -> Path:
            raw = (request.POST.get(field_name) or "").strip().strip('"')
            if not raw:
                raise ValueError(f"{field_name} is blank.")
            p = Path(raw)
            if not p.exists():
                raise ValueError(f"File not found: {p}")
            if not p.is_file():
                raise ValueError(f"Path is not a file (looks like a folder): {p}")
            return p

        out = StringIO()

        try:
            if action == "run_posting":
                entity_slug = (request.POST.get("entity_slug") or "").strip()
                ledger_xid = (request.POST.get("ledger_xid") or "").strip()
                year_post = int(request.POST.get("year") or year)

                if not entity_slug or not ledger_xid:
                    raise ValueError("entity_slug and ledger_xid are required for posting.")

                call_command(
                    "post_forbes_lawn_2025_invoices",
                    entity_slug=entity_slug,
                    ledger_xid=ledger_xid,
                    year=year_post,
                    stdout=out,
                )
                messages.success(request, "Posting completed.")

            elif action == "run_jobber_payments":
                csv_path = _validated_csv_path("jobber_payments_csv_path")
                dry_run = bool(request.POST.get("jobber_payments_dry_run"))

                # pass dry_run flag only if checked
                kwargs = {"stdout": out}
                if dry_run:
                    kwargs["dry_run"] = True

                call_command(
                    "import_jobber_payments",
                    str(csv_path),
                    **kwargs,
                )
                messages.success(request, "Jobber payments import completed.")

            elif action == "run_jobber_invoices":
                csv_path = _validated_csv_path("jobber_invoices_csv_path")
                dry_run = bool(request.POST.get("jobber_invoices_dry_run"))

                kwargs = {"stdout": out}
                if dry_run:
                    kwargs["dry_run"] = True

                call_command(
                    "import_jobber_invoices",
                    str(csv_path),
                    **kwargs,
                )
                messages.success(request, "Jobber invoices import completed.")

            else:
                messages.error(request, "Unknown action from Imports Hub.")

        except Exception as e:
            messages.error(request, f"Command failed: {e}")

        # Save console output for the page to display
        request.session["imports_last_output"] = out.getvalue()

        return redirect("forbes_lawn_dashboard:imports_hub")

    # -------------------------
    # GET: counts (your existing logic)
    # -------------------------

    inv_qs = Invoice.objects.filter(
        entity=entity,
        invoice_date__year=year,
        ar_journal_entry__isnull=True,
    )
    context["invoices_unposted_count"] = inv_qs.count()
    context["invoices_unposted_total"] = inv_qs.aggregate(t=Sum("total"))["t"] or Decimal("0.00")

    pay_qs = InvoicePayment.objects.filter(
        invoice__entity=entity,
        payment_date__year=year,
        payment_journal_entry__isnull=True,
    )
    context["payments_unposted_count"] = pay_qs.count()
    context["payments_unposted_total"] = pay_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

    st_qs = StagedTransactionModel.objects.filter(
        _entity_slug=entity.slug,
        created__year=year,
    )
    context["bank_staged_count"] = st_qs.count()
    context["bank_staged_total"] = st_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

    return render(request, "forbes_lawn_dashboard/imports_hub.html", context)


def accounting_hub(request):
    return render(request, "forbes_lawn_dashboard/accounting_hub.html", {"today": timezone.localdate()})
   