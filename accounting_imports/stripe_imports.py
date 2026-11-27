"""Stripe unified payments CSV staging. Never creates a sale or ledger entry."""
import csv
import io
import re
from datetime import datetime, timezone as utc
from decimal import Decimal, InvalidOperation
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render
from .models import StripePaymentImport, WooOrderImport
from .woo_payouts import processor_for

REQUIRED = {"id", "Created date (UTC)", "Amount", "Amount Refunded", "Currency", "Captured",
            "Fee", "Status", "Transfer", "order_id (metadata)", "Converted Currency",
            "Converted Amount", "Converted Amount Refunded", "Taxes On Fee"}


def money(raw):
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount < 0 or amount >= Decimal("1000000000000") or amount.as_tuple().exponent < -2:
            raise ValueError
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Invalid currency amount.")


def parse_csv(raw):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not REQUIRED.issubset(headers):
            raise ValidationError("Choose a Stripe unified payments CSV with order metadata and Transfer columns.")
        results = []
        ids = set()
        for i, row in enumerate(reader, start=2):
            if i > 10001 or None in row or any(v is None for v in row.values()):
                raise ValidationError("Invalid or oversized CSV.")
            try:
                charge = row["id"].strip()
                if not re.fullmatch(r"ch_[A-Za-z0-9]{1,177}", charge) or charge in ids:
                    raise ValidationError("Invalid or repeated charge ID.")
                ids.add(charge)
                created = datetime.strptime(row["Created date (UTC)"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc.utc)
                gross, fee, refunded = (money(row[k]) for k in ("Amount","Fee","Amount Refunded"))
                currency = row["Currency"].strip().lower()
                if currency != "usd" or row["Converted Currency"].strip().lower() != "usd":
                    raise ValidationError("Only USD payments without currency conversion are supported.")
                if money(row["Converted Amount"]) != gross or money(row["Converted Amount Refunded"]) != refunded or refunded > gross:
                    raise ValidationError("Converted amounts or refunds are inconsistent.")
                captured = row["Captured"].strip().lower()
                if captured not in ("true","false"):
                    raise ValidationError("Invalid captured flag.")
                status = row["Status"].strip()
                if not status or len(status)>40:
                    raise ValidationError("Invalid status.")
                payout = row["Transfer"].strip()
                if payout and not re.fullmatch(r"po_[A-Za-z0-9]{1,177}", payout):
                    raise ValidationError("Unsupported Transfer reference; expected a payout ID.")
                order = row["order_id (metadata)"].strip()
                if order and (not re.fullmatch(r"[0-9]{1,18}",order) or int(order)==0):
                    raise ValidationError("Invalid WooCommerce order ID.")
                def field(key, limit):
                    value = row.get(key,"").strip()
                    if len(value)>limit:
                        raise ValidationError("Field exceeds supported length: " + key)
                    return value
                email = field("Customer Email",254) or field("customer_email (metadata)",254)
                source = {"site_url":field("site_url (metadata)",500),
                          "tax_metadata":field("tax_amount (metadata)",100),
                          "tax_on_fee":str(money(row["Taxes On Fee"])),
                          "statement_descriptor":field("Statement Descriptor",200),
                          "invoice_id":field("Invoice ID",180)}
                results.append(dict(charge_id=charge,created_utc=created,gross=gross,fee=fee,refunded=refunded,
                    currency=currency,payment_status=status,captured=captured=="true",payout_id=payout,
                    woo_order_number=int(order) if order else None,customer_name=field("customer_name (metadata)",200),
                    customer_email=email,customer_reference=field("Customer ID",180),
                    description=field("Description",500),source_details=source))
            except (ValidationError, ValueError) as exc:
                raise ValidationError(f"CSV row {i}: {exc}") from exc
        if not results:
            raise ValidationError("No payment rows found.")
        return results
    except (UnicodeError,csv.Error) as exc:
        raise ValidationError("Invalid UTF-8 CSV.") from exc


@transaction.atomic
def stage(raw, actor):
    added = skipped = 0
    for fields in parse_csv(raw):
        charge = fields["charge_id"]
        record, created = StripePaymentImport.objects.get_or_create(charge_id=charge, defaults={**fields,"imported_by":actor})
        if created:
            added += 1
        elif any(getattr(record,k)!=v for k,v in fields.items()):
            raise ValidationError(f"Existing charge {charge} has changed. No rows imported; review the changed export before proceeding.")
        else:
            skipped += 1
    return added, skipped


def classify(payment):
    """Dynamic read-only association, not a revenue record."""
    if payment.payment_status.casefold() != "paid" or not payment.captured or payment.refunded or payment.gross <= 0:
        return "Further review — unpaid or refunded", None
    refs = list(WooOrderImport.objects.filter(payment_reference=payment.charge_id))
    if payment.woo_order_number:
        order = WooOrderImport.objects.filter(source_order_id=payment.woo_order_number).first()
        if not order:
            return "Waiting for WooCommerce order", None
        if (any(o.pk != order.pk for o in refs) or order.total != payment.gross or
            processor_for(order) != "Stripe" or order.review_status == WooOrderImport.EXCLUDED or
            order.woo_status not in ("completed","processing") or order.payload.get("refunds") or
            (order.payment_reference.startswith("ch_") and order.payment_reference != payment.charge_id)):
            return "WooCommerce conflict — review", order
        if StripePaymentImport.objects.filter(woo_order_number=payment.woo_order_number,captured=True,payment_status__iexact="paid").exclude(pk=payment.pk).exists():
            return "Multiple charges for order — review", order
        return "WooCommerce linked — no new sale", order
    if refs or payment.source_details.get("site_url") or re.search(r"\bO\s*#\d+",payment.source_details.get("statement_descriptor",""),re.I):
        return "Possible WooCommerce payment — review", refs[0] if len(refs)==1 else None
    return "Possible direct sale — review required", None


class UploadForm(forms.Form):
    file = forms.FileField(label="Stripe payments CSV")
    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv") or f.size>5_000_000:
            raise ValidationError("Choose a CSV file up to 5 MB.")
        return f


@staff_member_required(login_url="/admin/login/")
def inbox(request):
    form = UploadForm(request.POST or None,request.FILES or None)
    result = None
    if request.method=="POST" and form.is_valid():
        try:
            added, skipped = stage(form.cleaned_data["file"].read(),request.user)
        except ValidationError as exc:
            form.add_error("file",exc)
        else:
            result={"added":added,"skipped":skipped}
            form=UploadForm()
    payments=list(StripePaymentImport.objects.all()[:200])
    for p in payments:
        p.review_label,p.woo_order=classify(p)
        p.net=p.gross-p.fee
    return render(request,"accounting_imports/stripe_inbox.html",{"form":form,"result":result,"payments":payments})
