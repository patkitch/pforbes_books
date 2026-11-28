"""Verified manual staging from Stripe balance transaction evidence, not a refund API."""
import re
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction, IntegrityError
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import StripeAdjustment, StripePaymentImport, StripeGroupMatch, StripePayoutMatch, WooPayoutMatch, WooOrderImport
from .woo_payouts import processor_for
from accounting_contacts.models import Receipt

ZERO=Decimal("0.00")

def active_adjustments(payout_id):
    return StripeAdjustment.objects.filter(payout_id=payout_id,voided_at__isnull=True)

def payout_matched(payout_id):
    return (StripeGroupMatch.objects.filter(payout_id=payout_id,undone_at__isnull=True).exists() or
        StripePayoutMatch.objects.filter(payout_id=payout_id,undone_at__isnull=True).exists() or
        WooPayoutMatch.objects.filter(undone_at__isnull=True,order__source_order_id__in=StripePaymentImport.objects.filter(payout_id=payout_id,woo_order_number__isnull=False).values("woo_order_number")).exists())

def allocation(p):
    if p.currency.upper()!="USD" or not p.captured or p.gross<=0 or p.review_data.get("state")=="excluded":
        raise forms.ValidationError("Original payment is not an eligible USD business payment.")
    if p.woo_order_number:
        o=WooOrderImport.objects.filter(source_order_id=p.woo_order_number).first()
        if not o or o.total!=p.gross or o.review_status==WooOrderImport.EXCLUDED or processor_for(o)!="Stripe" or o.payload.get("currency")!="USD" or (o.payment_reference.startswith("ch_") and o.payment_reference!=p.charge_id):
            raise forms.ValidationError("Original WooCommerce sale is unresolved.")
        if StripePaymentImport.objects.filter(woo_order_number=p.woo_order_number,captured=True).exclude(pk=p.pk).exists():
            raise forms.ValidationError("Multiple charges for original order require separate review.")
        values=(o.total-o.shipping_total-o.tax_total,o.shipping_total,o.tax_total)
    else:
        data=p.review_data
        if p.source_details.get("site_url") or WooOrderImport.objects.filter(payment_reference=p.charge_id).exists() or data.get("state")!="reviewed" or not Receipt.objects.filter(pk=data.get("receipt_id"),source="stripe_direct",source_reference=p.charge_id,amount=p.gross).exists():
            raise forms.ValidationError("Original direct sale must have a verified receipt.")
        try:
            values=(Decimal(str(data["unit_price"]))*int(data["quantity"]),Decimal(str(data["shipping"])),Decimal(str(data["tax"])))
        except (KeyError,ValueError,TypeError,InvalidOperation):
            raise forms.ValidationError("Original sale allocation missing.")
    if any(not v.is_finite() or v<0 for v in values) or sum(values,ZERO)!=p.gross:
        raise forms.ValidationError("Original sale allocation is inconsistent.")
    return values

class AdjustmentForm(forms.Form):
    kind=forms.ChoiceField(choices=StripeAdjustment._meta.get_field("kind").choices)
    balance_id=forms.RegexField(r"^txn_[A-Za-z0-9]+$",max_length=180,label="Stripe balance transaction ID")
    refund_id=forms.RegexField(r"^re_[A-Za-z0-9]+$",max_length=180,required=False)
    charge_id=forms.RegexField(r"^ch_[A-Za-z0-9]+$",max_length=180,required=False,label="Original charge ID (refund only)")
    payout_id=forms.RegexField(r"^po_[A-Za-z0-9]+$",max_length=180,label="Payout containing this adjustment")
    day=forms.DateField(widget=forms.DateInput(attrs={"type":"date"}),label="Adjustment date (local)")
    artwork=forms.DecimalField(max_digits=14,decimal_places=2,min_value=0,initial=0,label="Artwork refunded")
    shipping=forms.DecimalField(max_digits=14,decimal_places=2,min_value=0,initial=0,label="Shipping refunded")
    tax=forms.DecimalField(max_digits=14,decimal_places=2,min_value=0,initial=0,label="Tax refunded")
    amount=forms.DecimalField(max_digits=14,decimal_places=2,label="Signed Stripe gross amount")
    fee=forms.DecimalField(max_digits=14,decimal_places=2,label="Signed Stripe fee (positive cost, negative credit)")
    net=forms.DecimalField(max_digits=14,decimal_places=2,label="Signed Stripe net")
    evidence=forms.CharField(max_length=500,widget=forms.Textarea)
    confirm=forms.BooleanField(label="I verified this successful USD transaction against Stripe's itemized payout or balance transaction evidence.")

    def clean(self):
        d=super().clean()
        if self.errors:
            return d
        if d["amount"]-d["fee"]!=d["net"] or not d["net"]:
            raise forms.ValidationError("Stripe gross minus fee must equal nonzero net.")
        total=sum((d[k] for k in ("artwork","shipping","tax")),ZERO)
        if d["kind"]=="refund":
            if not d["charge_id"] or not d["refund_id"] or total<=0 or d["amount"]!=-total:
                raise forms.ValidationError("Refund requires original charge, refund ID, and allocations equal to the negative gross.")
        elif d["charge_id"] or d["refund_id"] or total or d["amount"]!=0:
            raise forms.ValidationError("Standalone fee or credit must have zero gross, no sale allocation, and no charge or refund ID.")
        return d

@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def review(request):
    form=AdjustmentForm(request.POST or None)
    if request.method=="POST":
        if request.POST.get("action")=="void":
            a=get_object_or_404(StripeAdjustment.objects.select_for_update(),pk=request.POST.get("pk"))
            reason=request.POST.get("reason","").strip()
            from .posting import sale_posted
            if sale_posted("adjustment",a.pk) or a.voided_at or payout_matched(a.payout_id) or not reason or len(reason)>500 or request.POST.get("confirm")!="yes":
                return HttpResponseBadRequest("Undo payout first; explicit confirmation and reason required.")
            a.voided_at=timezone.now()
            a.voided_by=request.user
            a.void_reason=reason
            a.save(update_fields=["voided_at","voided_by","void_reason"])
            return redirect("accounting:stripe_adjustments")
        if form.is_valid():
            d=form.cleaned_data.copy()
            d.pop("confirm")
            charge=d.pop("charge_id")
            d["refund_id"]=d["refund_id"] or None
            try:
                # Lock imported charges for the affected payout and original payment.
                locked=list(StripePaymentImport.objects.select_for_update().filter(payout_id=d["payout_id"]).order_by("pk"))
                p=StripePaymentImport.objects.select_for_update().filter(charge_id=charge).first() if charge else None
                if not locked or payout_matched(d["payout_id"]):
                    raise forms.ValidationError("Import the affected payout charges first and undo any existing match for that payout.")
                if charge:
                    if not p or d["day"]<p.created_utc.astimezone(ZoneInfo("America/Chicago")).date():
                        raise forms.ValidationError("Original payment missing or refund date precedes sale.")
                    limits=allocation(p)
                    existing=p.adjustments.filter(voided_at__isnull=True)
                    for k,limit in zip(("artwork","shipping","tax"),limits):
                        if sum((getattr(a,k) for a in existing),ZERO)+d[k]>limit:
                            raise forms.ValidationError("Cumulative refund exceeds original "+k+" amount.")
                with transaction.atomic():
                    StripeAdjustment.objects.create(payment=p,created_by=request.user,**d)
            except IntegrityError:
                form.add_error(None,"Balance transaction or refund ID already recorded, including voided records.")
            except forms.ValidationError as e:
                form.add_error(None,e)
            else:
                return redirect("accounting:stripe_adjustments")
    return render(request,"accounting_imports/stripe_adjustments.html",{"form":form,"rows":StripeAdjustment.objects.select_related("payment","created_by","voided_by").order_by("-day","-pk")})
