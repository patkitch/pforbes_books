"""Explicit staff-only classification. No ledger posting."""
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from accounting.models import Account
from accounting_contacts.models import Vendor, Receipt
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
    receipt = forms.ModelChoiceField(queryset=Receipt.objects.none(), required=False,
                                      label="Existing purchase receipt (optional)")
    remember = forms.BooleanField(required=False, label="Remember this vendor and category for this exact bank description")

    def __init__(self, *args, row, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["category"].queryset = Account.objects.filter(is_active=True, account_type__in=(
            "expense", "cogs", "other_expense", "income", "other_income"))
        self.fields["receipt"].queryset = Receipt.objects.filter(
            receipt_type="purchase", journal_entry_id__isnull=True, amount=abs(row.amount),
            date=row.transaction_date)

    def clean(self):
        data = super().clean()
        kind = data.get("classification")
        vendor, name, category = data.get("vendor"), data.get("new_vendor"), data.get("category")
        receipt = data.get("receipt")
        if name and (vendor or Vendor.objects.filter(name__iexact=name).exists()):
            self.add_error("new_vendor", "Select the existing vendor instead.")
        if kind == "expense":
            if self.row.amount >= 0:
                self.add_error("classification", "Use further review for credits or refunds.")
            if not vendor and not name:
                self.add_error("vendor", "Select or create a vendor.")
            if not category or category.account_type not in ("expense", "cogs", "other_expense"):
                self.add_error("category", "Select an expense or cost of goods sold account.")
            if receipt and receipt.vendor_id and (not vendor or receipt.vendor_id != vendor.pk):
                self.add_error("receipt", "Receipt belongs to a different vendor.")
        elif kind == "income":
            if self.row.amount <= 0:
                self.add_error("classification", "Income must be a positive deposit.")
            if not category or category.account_type not in ("income", "other_income"):
                self.add_error("category", "Select an income account.")
            if vendor or name or receipt or data.get("remember"):
                self.add_error("classification", "Vendor and receipt options are for expenses only.")
        elif vendor or name or category or receipt or data.get("remember"):
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
    form = BankReviewForm(request.POST or None, row=row, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        vendor = data.get("vendor")
        if data.get("new_vendor"):
            vendor = Vendor.objects.create(name=data["new_vendor"])
        row.review_data = {
            "classification": data["classification"],
            "vendor": vendor.pk if vendor else None,
            "category": data["category"].pk if data.get("category") else None,
            "receipt": data["receipt"].pk if data.get("receipt") else None,
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
                  {"row": row, "account": account, "form": form})
