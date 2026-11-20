"""Offline WooCommerce import review screen: test fixtures only, no live API."""
import json
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .models import WooOrderImport
from .woo_orders import stage_orders, create_reviewed_receipt


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
    if request.method == "POST" and form.is_valid():
        try:
            data = json.loads(form.cleaned_data["file"].read().decode("utf-8-sig"))
            added, skipped = stage_orders(data)
        except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            form.add_error("file", str(exc))
        else:
            result = {"added": added, "skipped": skipped}
            form = WooOrderUploadForm()
    return render(request, "accounting_imports/woo_inbox.html", {
        "form": form, "result": result,
        "orders": WooOrderImport.objects.order_by("-order_date", "-pk")[:200],
    })


@require_POST
@staff_member_required(login_url="/admin/login/")
def woo_action(request, pk):
    record = get_object_or_404(WooOrderImport, pk=pk)
    action = request.POST.get("action")
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
