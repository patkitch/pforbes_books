"""Explicit, reversible bank/card pairing. No journal posting."""
from datetime import timedelta
import re
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from accounting.import_preview import eligible_import_accounts
from accounting_contacts.models import Receipt
from .models import ImportRow, CardPaymentMatch

MATCH_DAYS = 7


def active_match(row_id):
    return CardPaymentMatch.objects.filter(undone_at__isnull=True).filter(
        Q(bank_row_id=row_id) | Q(card_row_id=row_id))


def has_documents(row):
    return bool(row.review_data.get("receipt")) or Receipt.objects.filter(
        source="bank_document", source_reference__startswith=f"{row.pk}:").exists()


def confirmation(description):
    match = re.search(r"\b(?:confirmation|conf)\s*#\s*([a-z0-9-]+)", description, re.I)
    return match.group(1).casefold() if match else None


def candidates(bank):
    if bank.status != ImportRow.REVIEWED or bank.review_data.get("classification") != "card_payment" or bank.amount >= 0:
        return ImportRow.objects.none()
    if not eligible_import_accounts().filter(pk=bank.account_id, account_type="asset").exists():
        return ImportRow.objects.none()
    card = eligible_import_accounts().filter(pk=bank.review_data.get("payment_card"), account_type="liability").first()
    if not card or active_match(bank.pk).exists():
        return ImportRow.objects.none()
    stated = re.search(r"\b(?:CRD|CARD)\s+(\d{4})\b", bank.description, re.I)
    suffix = re.search(r"\((\d{4})\)\s*$", card.name)
    if stated and (not suffix or stated.group(1) != suffix.group(1)):
        return ImportRow.objects.none()
    used = CardPaymentMatch.objects.filter(undone_at__isnull=True)
    possible = ImportRow.objects.filter(account_id=card.pk, amount=-bank.amount,
        status=ImportRow.PENDING, transaction_date__range=(bank.transaction_date-timedelta(days=MATCH_DAYS),
        bank.transaction_date+timedelta(days=MATCH_DAYS)),
        ).exclude(
        pk__in=used.values("card_row_id")).exclude(pk__in=used.values("bank_row_id")).order_by("transaction_date", "pk")
    bank_ref = confirmation(bank.description)
    eligible = []
    for candidate in possible:
        if not re.search(r"\b(?:payment|pymt|pmt)\b", candidate.description, re.I):
            continue
        card_ref = confirmation(candidate.description)
        if bank_ref and card_ref and bank_ref != card_ref:
            continue
        eligible.append(candidate.pk)
    return possible.filter(pk__in=eligible)


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def match_payment(request, pk):
    if request.method == "POST" and request.POST.get("action") == "match":
        raw = request.POST.get("card_row", "")
        if not raw.isdecimal() or len(raw) > 18 or int(raw) == pk:
            return HttpResponseBadRequest("Select a valid card payment.")
        locked = {r.pk:r for r in ImportRow.objects.select_for_update().filter(pk__in=[pk,int(raw)]).order_by("pk")}
        bank, card = locked.get(pk), locked.get(int(raw))
        if not bank or not card or not candidates(bank).filter(pk=card.pk).exists() or has_documents(card) or has_documents(bank):
            return HttpResponseBadRequest("Match unavailable. Refresh and verify both records.")
        if card.review_data and card.review_data.get("classification") != "deferred":
            return HttpResponseBadRequest("Card record has an existing classification.")
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("Confirm the two records are the same payment.")
        CardPaymentMatch.objects.create(bank_row=bank, card_row=card, created_by=request.user)
        return redirect("accounting:payment_match", pk=pk)
    row = get_object_or_404(ImportRow, pk=pk)
    if request.method == "POST":
        if request.POST.get("action") != "undo" or request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("Confirm undo.")
        match = active_match(pk).first()
        if not match:
            return HttpResponseBadRequest("No active match.")
        from .posting import row_posted
        if row_posted(match.bank_row_id) or row_posted(match.card_row_id):
            return HttpResponseBadRequest("Posted match is locked.")
        list(ImportRow.objects.select_for_update().filter(pk__in=[match.bank_row_id,match.card_row_id]).order_by("pk"))
        match = CardPaymentMatch.objects.select_for_update().filter(pk=match.pk, undone_at__isnull=True).first()
        if not match:
            return HttpResponseBadRequest("Match already undone.")
        match.undone_at = timezone.now()
        match.undone_by = request.user
        match.save(update_fields=["undone_at","undone_by"])
        return redirect("accounting:payment_match", pk=pk)
    match = active_match(pk).select_related("bank_row","card_row").first()
    choices = [c for c in candidates(row) if not has_documents(c) and (not c.review_data or c.review_data.get("classification") == "deferred")]
    history = CardPaymentMatch.objects.filter(Q(bank_row_id=pk)|Q(card_row_id=pk)).order_by("-created_at")
    return render(request,"accounting_imports/payment_match.html",{"row":row,"match":match,"choices":choices,"history":history})
