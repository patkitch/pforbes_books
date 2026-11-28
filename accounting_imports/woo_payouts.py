"""Review-only individual order payouts. No accounting entries."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounting.import_preview import eligible_import_accounts
from accounting.models import Account
from .models import ImportRow, WooOrderImport, WooPayoutMatch, StripePayoutMatch, StripeGroupMatch, StripePaymentImport
from .payment_matching import active_match, has_documents

PAYOUT_DAYS = 14
MAX_FEE_RATE = Decimal("0.10")


def active_payout(row_id):
    return WooPayoutMatch.objects.filter(bank_row_id=row_id, undone_at__isnull=True).first()


def processor_for(order):
    key = str(order.payload.get("payment_method") or "").casefold()
    title = order.payment_method.casefold()
    if key == "woocommerce_payments" or "woopayments" in title or "woocommerce in-person payments" in title:
        return "WooPayments"
    if key.startswith("stripe") or "stripe" in title:
        return "Stripe"
    return None


def paid_date(order):
    raw = order.payload.get("date_paid") or order.payload.get("date_paid_gmt")
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def eligible_order(order):
    return (order.review_status != WooOrderImport.EXCLUDED and order.woo_status in ("completed", "processing")
        and paid_date(order) and processor_for(order) and order.total > 0
        and order.payload.get("currency") == "USD" and not order.payload.get("refunds"))


def metadata_money(order, keys):
    for item in order.payload.get("meta_data") or []:
        if isinstance(item, dict) and item.get("key") in keys:
            try:
                value = Decimal(str(item.get("value")))
                if value.is_finite() and value >= 0 and value.as_tuple().exponent >= -2:
                    return value
            except (InvalidOperation, ValueError, TypeError):
                pass
    return None


def candidates(order):
    if not eligible_order(order) or order.payout_matches.filter(undone_at__isnull=True).exists():
        return []
    if order.stripe_group_memberships.filter(group__undone_at__isnull=True).exists():
        return []
    if processor_for(order) == "Stripe":
        for p in StripePaymentImport.objects.filter(woo_order_number=order.source_order_id).exclude(payout_id=""):
            from .stripe_adjustments import active_adjustments
            if active_adjustments(p.payout_id).exists() or StripePaymentImport.objects.filter(payout_id=p.payout_id).exclude(pk=p.pk).exists():
                return []
    processor = processor_for(order)
    paid = paid_date(order)
    known_fee = metadata_money(order, ("_stripe_fee", "Stripe Fee")) if processor == "Stripe" else None
    known_net = metadata_money(order, ("_stripe_net", "Stripe Payout")) if processor == "Stripe" else None
    rows = ImportRow.objects.filter(account_id__in=eligible_import_accounts().filter(account_type="asset").values("pk"),
        status=ImportRow.PENDING, amount__gt=0, amount__lte=order.total,
        amount__gte=order.total*(1-MAX_FEE_RATE), transaction_date__range=(paid, paid+timedelta(days=PAYOUT_DAYS)))
    rows = rows.exclude(pk__in=WooPayoutMatch.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    rows = rows.exclude(pk__in=StripePayoutMatch.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    rows = rows.exclude(pk__in=StripeGroupMatch.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    result = []
    account_names = {a.pk: str(a) for a in eligible_import_accounts().filter(account_type="asset")}
    for row in rows.order_by("transaction_date", "pk"):
        if not re.search(r"\b" + re.escape(processor) + r"\b", row.description, re.I):
            continue
        if row.review_data and row.review_data.get("classification") != "deferred":
            continue
        if active_match(row.pk).exists() or has_documents(row):
            continue
        fee = order.total - row.amount
        if (known_fee is not None and fee != known_fee) or (known_net is not None and row.amount != known_net):
            continue
        row.account_label = account_names.get(row.account_id, f"Account #{row.account_id}")
        row.calculated_fee = fee
        result.append(row)
    return result


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def reconcile(request, pk):
    order = get_object_or_404(WooOrderImport.objects.select_for_update(), pk=pk)
    member = order.stripe_group_memberships.filter(group__undone_at__isnull=True).select_related("group").first()
    if member:
        return redirect("accounting:stripe_group",payout_id=member.group.payout_id)
    match = order.payout_matches.filter(undone_at__isnull=True).select_related("bank_row").first()
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("Explicit confirmation is required.")
        action = request.POST.get("action")
        if action == "undo" and match:
            ImportRow.objects.select_for_update().get(pk=match.bank_row_id)
            match.undone_at = timezone.now()
            match.undone_by = request.user
            match.save(update_fields=["undone_at", "undone_by"])
            return redirect("accounting:woo_payout", pk=pk)
        if action != "match" or match:
            return HttpResponseBadRequest("Invalid payout action.")
        raw = request.POST.get("bank_row", "")
        if not raw.isascii() or not raw.isdecimal() or len(raw)>18:
            return HttpResponseBadRequest("Select a deposit.")
        bank = ImportRow.objects.select_for_update().filter(pk=int(raw)).first()
        if not bank or not any(row.pk == bank.pk for row in candidates(order)):
            return HttpResponseBadRequest("Deposit no longer eligible. Refresh and verify.")
        evidence = request.POST.get("evidence", "").strip()
        if not evidence or len(evidence)>500:
            return HttpResponseBadRequest("Record how the processor payment and fee were verified (up to 500 characters).")
        WooPayoutMatch.objects.create(order=order, bank_row=bank, processor=processor_for(order),
            gross=order.total, fee=order.total-bank.amount, net=bank.amount, evidence=evidence, created_by=request.user)
        return redirect("accounting:woo_payout", pk=pk)
    matched_account = Account.objects.filter(pk=match.bank_row.account_id).first() if match else None
    return render(request, "accounting_imports/woo_payout.html", {"order":order, "match":match,
        "matched_account":matched_account, "choices":candidates(order), "processor":processor_for(order), "paid":paid_date(order),
        "eligible":eligible_order(order), "artwork":order.total-order.shipping_total-order.tax_total,
        "history":order.payout_matches.order_by("-created_at")})
