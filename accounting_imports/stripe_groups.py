"""Review-only exact grouped Stripe payouts. No refunds or adjustments."""
from datetime import timedelta
from decimal import Decimal
import re
from zoneinfo import ZoneInfo
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from accounting.import_preview import eligible_import_accounts
from accounting_contacts.models import Receipt
from .models import ImportRow, StripePaymentImport, StripePayoutMatch, WooPayoutMatch, StripeGroupMatch, StripeGroupMember, WooOrderImport
from .payment_matching import active_match, has_documents
from .stripe_imports import classify
from .woo_payouts import eligible_order, metadata_money

ZERO=Decimal("0.00")

def active_group(row_id):
    return StripeGroupMatch.objects.filter(bank_row_id=row_id,undone_at__isnull=True).first()

def inspect_group(payments):
    items=[]
    errors=[]
    if len(payments)<2:
        errors.append("At least two imported charges with the same payout ID are required.")
    seen=set()
    for p in payments:
        label,order=classify(p)
        reason=""
        if p.currency.upper()!="USD" or not p.captured or p.refunded or p.payment_status.casefold()!="paid" or not 0<=p.fee<p.gross:
            reason="Unsupported currency, payment, fee or refund."
        elif StripePayoutMatch.objects.filter(payment=p,undone_at__isnull=True).exists() or p.group_memberships.filter(group__undone_at__isnull=True).exists():
            reason="Charge already matched."
        elif label=="WooCommerce linked — no new sale":
            known_fee=metadata_money(order,("_stripe_fee","Stripe Fee"))
            known_net=metadata_money(order,("_stripe_net","Stripe Payout"))
            if not eligible_order(order) or order.pk in seen or order.total<order.shipping_total+order.tax_total or min(order.shipping_total,order.tax_total)<0 or (known_fee is not None and known_fee!=p.fee) or (known_net is not None and known_net!=p.gross-p.fee) or order.payout_matches.filter(undone_at__isnull=True).exists() or order.stripe_group_memberships.filter(group__undone_at__isnull=True).exists():
                reason="Order not eligible, conflicting amounts or already matched."
            seen.add(order.pk)
        elif label=="Possible direct sale — review required":
            if p.review_data.get("state")!="reviewed" or not Receipt.objects.filter(pk=p.review_data.get("receipt_id"),source="stripe_direct",source_reference=p.charge_id,amount=p.gross).exists():
                reason="Direct sale must have a verified internal receipt."
        else:
            reason=label
        if reason:
            errors.append(p.charge_id+": "+reason)
        items.append(dict(payment=p,order=order,customer=order.customer_name if order else p.review_data.get("customer_name") or p.customer_name,net=p.gross-p.fee,reason=reason))
    return items,errors

def candidates(payments,items,errors):
    if errors or not payments:
        return []
    payout=payments[0].payout_id
    if StripeGroupMatch.objects.filter(payout_id=payout,undone_at__isnull=True).exists() or StripePayoutMatch.objects.filter(payout_id=payout,undone_at__isnull=True).exists():
        return []
    net=sum((i["net"] for i in items),ZERO)
    latest=max(p.created_utc.astimezone(ZoneInfo("America/Chicago")).date() for p in payments)
    accounts=eligible_import_accounts().filter(account_type="asset")
    rows=ImportRow.objects.filter(account_id__in=accounts.values("pk"),status=ImportRow.PENDING,amount=net,
        transaction_date__range=(latest,latest+timedelta(days=14)),batch__undone_at__isnull=True)
    for model in (StripeGroupMatch,StripePayoutMatch,WooPayoutMatch):
        rows=rows.exclude(pk__in=model.objects.filter(undone_at__isnull=True).values("bank_row_id"))
    names={a.pk:str(a) for a in accounts}
    result=[]
    for r in rows:
        if re.search(r"\bstripe\b",r.description,re.I) and (not r.review_data or r.review_data.get("classification")=="deferred") and not active_match(r.pk).exists() and not has_documents(r):
            r.account_label=names[r.account_id]
            result.append(r)
    return result

@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def reconcile(request,payout_id):
    if not re.fullmatch(r"po_[A-Za-z0-9]{1,177}",payout_id):
        return HttpResponseBadRequest("Invalid payout ID.")
    payments=list(StripePaymentImport.objects.select_for_update().filter(payout_id=payout_id).order_by("pk"))
    if not payments:
        return HttpResponseBadRequest("Unknown payout.")
    # Individual order matching and exclusion lock the same order rows.
    list(WooOrderImport.objects.select_for_update().filter(source_order_id__in=[p.woo_order_number for p in payments if p.woo_order_number]).order_by("pk"))
    match=StripeGroupMatch.objects.filter(payout_id=payout_id,undone_at__isnull=True).select_related("bank_row").first()
    if request.method=="POST":
        if request.POST.get("confirm")!="yes":
            return HttpResponseBadRequest("Confirmation required.")
        if request.POST.get("action")=="undo" and match:
            ImportRow.objects.select_for_update().get(pk=match.bank_row_id)
            match.undone_at=timezone.now()
            match.undone_by=request.user
            match.save(update_fields=["undone_at","undone_by"])
            return redirect("accounting:stripe_group",payout_id=payout_id)
        if request.POST.get("action")!="match" or match:
            return HttpResponseBadRequest("Invalid group action.")
        raw=request.POST.get("bank_row","")
        evidence=request.POST.get("evidence","").strip()
        if not raw.isascii() or not raw.isdecimal() or len(raw)>18 or not evidence or len(evidence)>500:
            return HttpResponseBadRequest("Select a deposit and provide evidence.")
        bank=ImportRow.objects.select_for_update().filter(pk=int(raw)).first()
        items,errors=inspect_group(payments)
        if not bank or not any(r.pk==bank.pk for r in candidates(payments,items,errors)):
            return HttpResponseBadRequest("Group or deposit unavailable. Refresh and verify.")
        gross=sum((p.gross for p in payments),ZERO)
        fee=sum((p.fee for p in payments),ZERO)
        group=StripeGroupMatch.objects.create(payout_id=payout_id,bank_row=bank,gross=gross,fee=fee,net=bank.amount,evidence=evidence,created_by=request.user)
        StripeGroupMember.objects.bulk_create([StripeGroupMember(group=group,payment=i["payment"],order=i["order"],gross=i["payment"].gross,fee=i["payment"].fee,net=i["net"]) for i in items])
        return redirect("accounting:stripe_group",payout_id=payout_id)
    items,errors=inspect_group(payments)
    return render(request,"accounting_imports/stripe_group.html",dict(payout_id=payout_id,items=items,errors=errors,match=match,
        choices=candidates(payments,items,errors),gross=sum((p.gross for p in payments),ZERO),fee=sum((p.fee for p in payments),ZERO),
        net=sum((i["net"] for i in items),ZERO),history=StripeGroupMatch.objects.filter(payout_id=payout_id).prefetch_related("members").order_by("-created_at")))
