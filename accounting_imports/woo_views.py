"""Staff-reviewed WooCommerce imports from fixtures or opt-in read-only API."""
import json
from django.db import transaction
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .models import WooOrderImport, WooPayoutMatch
from .woo_payouts import eligible_order
from .woo_orders import stage_orders, create_reviewed_receipt
from .woo_client import configured, fetch_and_stage, WooConnectionError


class WooFetchForm(forms.Form):
    days = forms.TypedChoiceField(coerce=int, choices=[(7, "Last 7 days"), (30, "Last 30 days"), (90, "Last 90 days")], initial=30)


class WooOrderUploadForm(forms.Form):
    file = forms.FileField(
        label="WooCommerce test orders (.json)",
        help_text="Upload a JSON array of WooCommerce order objects. Max 1 MB; test data only.",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".json") or f.size > 1_000_000:
            raise forms.ValidationError("Choose a JSON file no larger than 1 MB.")
        return f


@staff_member_required(login_url="/admin/login/")
def woo_inbox(request):
    form = WooOrderUploadForm(request.POST or None, request.FILES or None)
    result = None
    fetch_form = WooFetchForm(request.POST or None)
    connection_error = None
    if request.method == "POST" and request.POST.get("source") == "woocommerce":
        if not configured():
            connection_error = "WooCommerce connection is not enabled or configured."
        elif fetch_form.is_valid():
            try:
                added, skipped = fetch_and_stage(days=fetch_form.cleaned_data["days"])
            except (WooConnectionError, ValidationError) as exc:
                connection_error = str(exc)
            else:
                result = {"added": added, "skipped": skipped}
        form = WooOrderUploadForm()
    elif request.method == "POST" and form.is_valid():
        try:
            data = json.loads(form.cleaned_data["file"].read().decode("utf-8-sig"))
            added, skipped = stage_orders(data)
        except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            form.add_error("file", str(exc))
        else:
            result = {"added": added, "skipped": skipped}
            form = WooOrderUploadForm()
    orders = list(WooOrderImport.objects.order_by("-order_date", "-pk")[:200])
    matches = {m.order_id: m for m in WooPayoutMatch.objects.filter(undone_at__isnull=True, order_id__in=[o.pk for o in orders])}
    for order in orders:
        order.active_payout = matches.get(order.pk)
        order.payout_eligible = eligible_order(order)
    return render(request, "accounting_imports/woo_inbox.html", {
        "form": form, "result": result, "fetch_form": fetch_form,
        "connection_ready": configured(), "connection_error": connection_error,
        "orders": orders,
    })


@require_POST
@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def woo_action(request, pk):
    record = get_object_or_404(WooOrderImport.objects.select_for_update(), pk=pk)
    from .posting import sale_posted
    if sale_posted("woo",record.pk):
        return HttpResponseBadRequest("Posted sale is locked.")
    action = request.POST.get("action")
    if action == "exclude" and (record.payout_matches.filter(undone_at__isnull=True).exists() or record.stripe_group_memberships.filter(group__undone_at__isnull=True).exists()):
        return HttpResponseBadRequest("Undo the payout match before excluding the order.")
    if action == "exclude" and record.review_status == WooOrderImport.PENDING:
        record.review_status = WooOrderImport.EXCLUDED
        record.save(update_fields=["review_status"])
    elif action == "restore" and record.review_status == WooOrderImport.EXCLUDED:
        record.review_status = WooOrderImport.PENDING
        record.save(update_fields=["review_status"])
    elif action == "receipt":
        try:
            create_reviewed_receipt(record)
        except ValidationError as exc:
            return HttpResponseBadRequest("; ".join(exc.messages))
    else:
        return HttpResponseBadRequest("Invalid review action.")
    return redirect("accounting:woo_inbox")


@staff_member_required(login_url="/admin/login/")
def woo_detail(request, pk):
    record = get_object_or_404(WooOrderImport, pk=pk)
    payload = record.payload or {}
    metadata = {m.get("key"): m.get("value") for m in payload.get("meta_data", [])
                if isinstance(m, dict) and isinstance(m.get("key"), str)}
    def first(*keys):
        for key in keys:
            value = metadata.get(key)
            if value is not None and value != "":
                return value
        return None
    return render(request, "accounting_imports/woo_detail.html", {
        "order": record, "data": payload,
        "stripe_fee": first("_stripe_fee", "Stripe Fee"),
        "stripe_net": first("_stripe_net", "Stripe Payout"),
    })
