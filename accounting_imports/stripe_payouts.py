"""Review-only reconciliation of a verified single-charge Stripe payout."""
from datetime import timedelta
import re
from zoneinfo import ZoneInfo
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounting.import_preview import eligible_import_accounts
from accounting_contacts.models import Receipt
from .models import ImportRow, StripePaymentImport, StripePayoutMatch, WooPayoutMatch
from .payment_matching import active_match, has_documents
from .stripe_imports import classify


def eligible(payment):
    return (classify(payment)[0] == "Possible direct sale — review required"
        and payment.review_data.get("state") == "reviewed"
        and Receipt.objects.filter(source="stripe_direct", source_reference=payment.charge_id,
                                   pk=payment.review_data.get("receipt_id")).exists()
        and payment.currency.upper() == "USD" and 0 <= payment.fee < payment.gross
        and bool(payment.payout_id.strip())
        and not StripePaymentImport.objects.filter(payout_id=payment.payout_id).exclude(pk=payment.pk).exists())


def active_stripe_payout(row_id):
    return StripePayoutMatch.objects.filter(bank_row_id=row_id, undone_at__isnull=True).first()


def candidates(payment):
    if not eligible(payment) or StripePayoutMatch.objects.filter(payout_id=payment.payout_id, undone_at__isnull=True).exists():
        return []
    paid = payment.created_utc.astimezone(ZoneInfo("America/Chicago")).date()
    accounts = eligible_import_accounts().filter(account_type="asset")
    rows = ImportRow.objects.filter(account_id__in=accounts.values("pk"), status=ImportRow.PENDING,
        amount=payment.gross-payment.fee, transaction_date__range=(paid, paid+timedelta(days=14)),
        batch__undone_at__isnull=True)
    rows = rows.exclude(pk__in=StripePayoutMatch.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    rows = rows.exclude(pk__in=WooPayoutMatch.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    return [r for r in rows if re.search(r"\bstripe\b", r.description, re.I)
        and (not r.review_data or r.review_data.get("classification") == "deferred")
        and not active_match(r.pk).exists() and not has_documents(r)]


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def reconcile(request, pk):
    payment = get_object_or_404(StripePaymentImport.objects.select_for_update(), pk=pk)
    match = payment.payout_matches.filter(undone_at__isnull=True).select_related("bank_row").first()
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("Explicit confirmation required.")
        action = request.POST.get("action")
        if action == "undo" and match:
            ImportRow.objects.select_for_update().get(pk=match.bank_row_id)
            match.undone_at = timezone.now()
            match.undone_by = request.user
            match.save(update_fields=["undone_at", "undone_by"])
            return redirect("accounting:stripe_payout", pk=pk)
        if action != "match" or match:
            return HttpResponseBadRequest("Invalid payout action.")
        raw = request.POST.get("bank_row", "")
        evidence = request.POST.get("evidence", "").strip()
        if not raw.isascii() or not raw.isdecimal() or len(raw)>18 or not evidence or len(evidence)>500:
            return HttpResponseBadRequest("Select a deposit and provide verification evidence.")
        bank = ImportRow.objects.select_for_update().filter(pk=int(raw)).first()
        if not bank or not any(r.pk == bank.pk for r in candidates(payment)):
            return HttpResponseBadRequest("Deposit no longer eligible. Refresh and verify.")
        StripePayoutMatch.objects.create(payment=payment, bank_row=bank, payout_id=payment.payout_id,
            gross=payment.gross, fee=payment.fee, net=bank.amount, evidence=evidence, created_by=request.user)
        return redirect("accounting:stripe_payout", pk=pk)
    names = {a.pk:str(a) for a in eligible_import_accounts()}
    choices = candidates(payment)
    for row in choices:
        row.account_label = names.get(row.account_id, str(row.account_id))
    receipt = Receipt.objects.filter(source="stripe_direct", source_reference=payment.charge_id).select_related("customer").first()
    customer_name = (receipt.customer.name if receipt and receipt.customer else "") or payment.review_data.get("customer_name") or payment.customer_name or "Name not provided"
    return render(request, "accounting_imports/stripe_payout.html", {
        "customer_name":customer_name,
        "payment":payment, "match":match, "choices":choices, "eligible":eligible(payment),
        "net":payment.gross-payment.fee, "history":payment.payout_matches.order_by("-created_at")})
