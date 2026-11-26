"""Explicit staff-only classification. No ledger posting."""
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from accounting.models import Account
from accounting_contacts.models import Vendor, Receipt
from accounting_contacts.forms import ReceiptForm
from hashlib import sha256
from .models import ImportRow


class BankReviewForm(forms.Form):
    classification = forms.ChoiceField(choices=[
        ("expense", "Business expense"), ("income", "Business income"),
        ("personal", "Personal — exclude"), ("deferred", "Other — needs further review"),
    ])
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none(), required=False)
    new_vendor = forms.CharField(max_length=200, required=False, label="Or create vendor")
    category = forms.ModelChoiceField(queryset=Account.objects.none(), required=False,
                                      label="Chart of Accounts")
    memo = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))
    attachment = forms.FileField(required=False, label="Upload original receipt or invoice (optional)",
        help_text="PDF, JPG, PNG or WebP, up to 10 MB. You can add another document later.")
    remember = forms.BooleanField(required=False, label="Remember this vendor and category for this exact bank description")

    def __init__(self, *args, row, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["category"].queryset = Account.objects.filter(is_active=True, account_type__in=(
            "expense", "cogs", "other_expense", "income", "other_income"))
        self.documents = Receipt.objects.filter(source="bank_document",
            source_reference__startswith=f"{row.pk}:").order_by("pk")

    def clean_attachment(self):
        return ReceiptForm.clean_attachment(self)

    def clean(self):
        data = super().clean()
        kind = data.get("classification")
        vendor, name, category = data.get("vendor"), data.get("new_vendor"), data.get("category")
        attachment = data.get("attachment")
        documents = list(self.documents)
        legacy = self.row.review_data.get("receipt")
        if legacy:
            documents += list(Receipt.objects.filter(pk=legacy))
        if documents and (kind != "expense" or not vendor or any(d.vendor_id != vendor.pk for d in documents)):
            self.add_error("vendor", "Existing purchase documentation is linked to this vendor. Keep the vendor and expense classification.")
        if name and (vendor or Vendor.objects.filter(name__iexact=name).exists()):
            self.add_error("new_vendor", "Select the existing vendor instead.")
        if kind == "expense":
            if self.row.amount >= 0:
                self.add_error("classification", "Use further review for credits or refunds.")
            if not vendor and not name:
                self.add_error("vendor", "Select or create a vendor.")
            if not category or category.account_type not in ("expense", "cogs", "other_expense"):
                self.add_error("category", "Select an expense or cost of goods sold account.")

        elif kind == "income":
            if self.row.amount <= 0:
                self.add_error("classification", "Income must be a positive deposit.")
            if not category or category.account_type not in ("income", "other_income"):
                self.add_error("category", "Select an income account.")
            if vendor or name or attachment or data.get("remember"):
                self.add_error("classification", "Vendor and receipt options are for expenses only.")
        elif vendor or name or category or attachment or data.get("remember"):
            self.add_error("classification", "Clear accounting selections for personal or deferred items.")
        return data


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def review(request, pk):
    row = get_object_or_404(ImportRow.objects.select_for_update(), pk=pk)
    initial = dict(row.review_data)
    if not initial:
        # Only explicitly remembered exact descriptions suggest an assignment.
        candidates = ImportRow.objects.filter(description__iexact=row.description,
            account_id=row.account_id, status=ImportRow.REVIEWED).exclude(pk=pk).order_by("-pk")
        for candidate in candidates:
            saved = candidate.review_data
            if saved.get("remember") and saved.get("classification") == "expense":
                initial = {k: saved.get(k) for k in ("classification", "vendor", "category")}
                break
    form = BankReviewForm(request.POST or None, request.FILES or None, row=row, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        vendor = data.get("vendor")
        if data.get("new_vendor"):
            vendor = Vendor.objects.create(name=data["new_vendor"])
        upload = data.get("attachment")
        if upload:
            digest = sha256()
            for chunk in upload.chunks():
                digest.update(chunk)
            upload.seek(0)
            reference = f"{row.pk}:{digest.hexdigest()}"
            if not Receipt.objects.filter(source="bank_document", source_reference=reference).exists():
                Receipt.objects.create(title=f"{vendor.name} — purchase document"[:200],
                    receipt_type="purchase", date=row.transaction_date, amount=abs(row.amount),
                    vendor=vendor, source="bank_document", source_reference=reference,
                    attachment=upload, notes="Original document attached to bank transaction. Date and amount are from bank record.")
        row.review_data = {
            "classification": data["classification"],
            "vendor": vendor.pk if vendor else None,
            "category": data["category"].pk if data.get("category") else None,
            "receipt": row.review_data.get("receipt"),
            "memo": data.get("memo", ""),
            "remember": data.get("remember", False),
            "reviewed_by": request.user.pk,
        }
        row.status = {"personal": ImportRow.EXCLUDED, "deferred": ImportRow.PENDING}.get(
            data["classification"], ImportRow.REVIEWED)
        row.save(update_fields=["review_data", "status"])
        return redirect("accounting:import_inbox")
    account = Account.objects.filter(pk=row.account_id).first()
    return render(request, "accounting_imports/bank_review.html",
                  {"row": row, "account": account, "form": form,
                   "documents": form.documents, "legacy_receipt": row.review_data.get("receipt")})
