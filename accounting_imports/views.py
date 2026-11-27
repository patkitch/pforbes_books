"""Staff-only staged CSV inbox. No approval or journal posting yet."""
from collections import Counter
from hashlib import sha256

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Count
from django.core.paginator import Paginator
from django.urls import reverse
from urllib.parse import urlencode
from accounting_contacts.models import Vendor, Receipt
from django.utils import timezone
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounting.import_preview import ImportPreviewForm, parse_csv_preview, validate_statement_account
from accounting.models import Account
from .models import ImportBatch, ImportRow, CardPaymentMatch, WooPayoutMatch
from .payment_matching import active_match
from .woo_payouts import active_payout
from .stripe_payouts import active_stripe_payout
from .models import StripePayoutMatch


def _fingerprint(row):
    value = "|".join((
        row["date"].isoformat(),
        row["description"].strip().casefold(),
        f'{row["amount"]:.2f}',
    ))
    if row.get("source_format") == "boa_card" and row.get("reference"):
        value += "|boa_card|" + row["reference"]
    return sha256(value.encode("utf-8")).hexdigest()


@transaction.atomic
def stage_rows(account, filename, rows, actor=None):
    """Deduplicate per account while retaining legitimate identical rows in one statement."""
    batch = ImportBatch.objects.create(
        account_id=account.pk, filename=filename[:255], created_by=actor,
        statement_summary=getattr(rows, "summary", {}),
    )
    occurrences = Counter()
    added = skipped = 0
    for row in rows:
        fingerprint = _fingerprint(row)
        occurrences[fingerprint] += 1
        _, created = ImportRow.objects.get_or_create(
            account_id=account.pk,
            fingerprint=fingerprint,
            occurrence=occurrences[fingerprint],
            defaults={
                "batch": batch,
                "transaction_date": row["date"],
                "description": row["description"],
                "amount": row["amount"],
                "source_details": {k: row[k] for k in ("reference", "merchant_address", "running_balance", "source_format") if k in row},
            },
        )
        if created:
            added += 1
        else:
            skipped += 1
    return batch, added, skipped


@staff_member_required(login_url="/admin/login/")
def inbox(request):
    form = ImportPreviewForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            rows = parse_csv_preview(upload.read())
            validate_statement_account(form.cleaned_data["account"], upload.name, rows)
        except ValueError as exc:
            form.add_error("file", str(exc))
        else:
            selected = form.cleaned_data["account"]
            other_ids = set(ImportRow.objects.filter(
                fingerprint__in={_fingerprint(row) for row in rows}
            ).exclude(account_id=selected.pk).values_list("account_id", flat=True))
            warning = ", ".join(str(a) for a in Account.objects.filter(pk__in=other_ids))
            if other_ids and not warning:
                warning = "another financial account"
            _, added, skipped = stage_rows(
                form.cleaned_data["account"], upload.name, rows, request.user
            )
            result = {"added": added, "skipped": skipped, "summary": getattr(rows, "summary", {}), "cross_account_warning": warning}
            form = ImportPreviewForm()
    accounts = Account.objects.filter(pk__in=ImportRow.objects.values("account_id"))
    names = {account.pk: str(account) for account in accounts}
    queryset = ImportRow.objects.select_related("batch")
    account_filter = request.GET.get("account_filter", "")
    status_filter = request.GET.get("status_filter", "")
    if account_filter.isdecimal() and len(account_filter) <= 18:
        queryset = queryset.filter(account_id=int(account_filter))
    tab = request.GET.get("tab", "review")
    if tab not in ("review", "excluded", "posted"):
        tab = "review"
    if request.method == "POST":
        tab = "review"
    counts = dict(queryset.values("status").annotate(total=Count("pk")).values_list("status", "total"))
    tabs = [
        {"key": "review", "label": "To Review", "count": counts.get("pending", 0) + counts.get("reviewed", 0)},
        {"key": "excluded", "label": "Excluded", "count": counts.get("excluded", 0)},
        {"key": "posted", "label": "Posted", "count": 0},
    ]
    if tab == "review":
        queryset = queryset.filter(status__in=(ImportRow.PENDING, ImportRow.REVIEWED))
        if status_filter in (ImportRow.PENDING, ImportRow.REVIEWED):
            queryset = queryset.filter(status=status_filter)
    elif tab == "excluded":
        queryset = queryset.filter(status=ImportRow.EXCLUDED)
        status_filter = ""
    else:
        # No bank posting service exists yet. Never equate review with posting.
        queryset = queryset.none()
        status_filter = ""
    page = Paginator(queryset.order_by("-transaction_date", "-pk"), 50).get_page(request.GET.get("page"))
    items = list(page.object_list)
    vendors = Vendor.objects.in_bulk({i.review_data["vendor"] for i in items if i.review_data.get("vendor")})
    categories = Account.objects.in_bulk({i.review_data["category"] for i in items if i.review_data.get("category")})
    document_counts = Counter()
    for reference in Receipt.objects.filter(source="bank_document").values_list("source_reference", flat=True):
        prefix = reference.split(":", 1)[0]
        if prefix.isdecimal():
            document_counts[int(prefix)] += 1
    matched_ids = set()
    for bank_id, card_id in CardPaymentMatch.objects.filter(undone_at__isnull=True).values_list('bank_row_id','card_row_id'):
        matched_ids.update((bank_id,card_id))
    payouts = dict(WooPayoutMatch.objects.filter(undone_at__isnull=True, bank_row_id__in=[i.pk for i in items]).values_list('bank_row_id','order_id'))
    stripe_payouts = dict(StripePayoutMatch.objects.filter(undone_at__isnull=True, bank_row_id__in=[i.pk for i in items]).values_list('bank_row_id','payment_id'))
    for item in items:
        item.stripe_payment_id = stripe_payouts.get(item.pk)
        item.payout_order_id = payouts.get(item.pk)
        item.is_matched = item.pk in matched_ids
        item.account_label = names.get(item.account_id, f"Account #{item.account_id}")
        item.vendor_label = vendors.get(item.review_data.get("vendor"))
        item.category_label = categories.get(item.review_data.get("category"))
        if item.review_data.get("classification") == "split":
            item.category_label = "Split — business ${}, personal ${}".format(
                item.review_data.get("business_amount"), item.review_data.get("personal_amount"))
        if item.review_data.get("classification") == "card_payment":
            item.category_label = "Card payment — business ${}, {}".format(item.review_data.get("payment_business"), "Owner Investment" if item.review_data.get("payment_funding") == "personal" else "bank funded")
        if item.review_data.get("classification") == "gallery":
            item.vendor_label = item.review_data.get("gallery_name")
            item.category_label = "Gallery — gross ${}, commission ${}".format(item.review_data.get("gallery_gross"), item.review_data.get("gallery_commission"))
        item.document_count = document_counts[item.pk] + int(bool(item.review_data.get("receipt")))
        item.amount_label = ("−" if item.amount < 0 else "") + f"${abs(item.amount):,.2f}"
    for entry in tabs:
        entry["url"] = "?" + urlencode({"tab": entry["key"], "account_filter": account_filter})
    page_query = urlencode({"tab": tab, "account_filter": account_filter, "status_filter": status_filter})
    return render(request, "accounting_imports/inbox.html", {
        "form": form, "result": result, "items": items,
        "filter_accounts": accounts.order_by("number"), "filter_statuses": ImportRow.STATUSES,
        "account_filter": account_filter, "status_filter": status_filter,
        "tab": tab, "tabs": tabs, "page": page, "page_query": page_query,
    })


@require_POST
@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def change_status(request, pk):
    row = get_object_or_404(ImportRow.objects.select_for_update(), pk=pk)
    if active_payout(row.pk) or active_stripe_payout(row.pk):
        return HttpResponseBadRequest("Undo the payout match before changing status.")
    if active_match(row.pk).exists():
        return HttpResponseBadRequest("Undo the payment match before changing status.")
    target = request.POST.get("status")
    if target not in (ImportRow.PENDING, ImportRow.EXCLUDED):
        return HttpResponseBadRequest("Invalid status.")
    if row.status == ImportRow.REVIEWED:
        return HttpResponseBadRequest("Use transaction review to change a reviewed classification.")
    row.status = target
    row.review_data = {}
    row.save(update_fields=["status", "review_data"])
    params = {"tab": "review" if target == ImportRow.PENDING else request.POST.get("tab", "review")}
    if params["tab"] not in ("review", "excluded"):
        params["tab"] = "review"
    account_filter = request.POST.get("account_filter", "")
    if account_filter.isdecimal() and len(account_filter) <= 18:
        params["account_filter"] = account_filter
    return redirect(reverse("accounting:import_inbox") + "?" + urlencode(params))


def _undo_allowed(batch, rows):
    return not batch.undone_at and bool(rows) and all(
        row.status == ImportRow.PENDING and not row.review_data and not row.note
        and row.account_id == batch.account_id and not (row.bank_payment_matches.exists() or row.card_payment_matches.exists() or row.woo_payout_matches.exists() or row.stripe_payout_matches.exists()) for row in rows
    )


@staff_member_required(login_url="/admin/login/")
def batch_history(request):
    batches = list(ImportBatch.objects.annotate(row_count=Count("rows")).order_by("-pk"))
    names = dict((a.pk, str(a)) for a in Account.objects.filter(
        pk__in=[b.account_id for b in batches]))
    for batch in batches:
        batch.account_label = names.get(batch.account_id, f"Account #{batch.account_id}")
    return render(request, "accounting_imports/batches.html", {"batches": batches})


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def undo_batch(request, pk):
    batch = get_object_or_404(ImportBatch.objects.select_for_update(), pk=pk)
    rows = list(batch.rows.select_for_update().order_by("pk"))
    allowed = _undo_allowed(batch, rows)
    if request.method == "POST":
        if not allowed or request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("Undo not permitted. Only untouched pending imports can be undone.")
        count = len(rows)
        batch.rows.all().delete()
        batch.undone_at = timezone.now()
        batch.undone_by = request.user
        batch.undone_count = count
        batch.save(update_fields=["undone_at", "undone_by", "undone_count"])
        return redirect("accounting:batch_history")
    return render(request, "accounting_imports/undo_batch.html", {
        "batch": batch, "rows": rows, "allowed": allowed,
        "account": Account.objects.filter(pk=batch.account_id).first(),
    })
