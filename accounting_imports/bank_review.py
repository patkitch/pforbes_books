"""Explicit staff-only classification. No ledger posting."""
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from accounting.models import Account
from accounting.import_preview import eligible_import_accounts
from accounting_contacts.models import Vendor, Receipt
from accounting_contacts.forms import ReceiptForm
from hashlib import sha256
from .models import ImportRow
from .merchant_recognition import suggest
from .bank_splits import SplitFormSet, validate_allocations
from decimal import Decimal


class BankReviewForm(forms.Form):
    classification = forms.ChoiceField(choices=[
        ("", "Choose classification"), ("expense", "Business expense"), ("income", "Business income"),
        ("card_payment", "Credit card payment"), ("split", "Split purchase — business / personal"), ("personal", "Personal — exclude"), ("deferred", "Other — needs further review"),
    ])
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none(), required=False)
    new_vendor = forms.CharField(max_length=200, required=False, label="Add new vendor (if not listed)")
    category = forms.ModelChoiceField(queryset=Account.objects.none(), required=False,
                                      label="Expense / Income Category")
    memo = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))
    attachment = forms.FileField(required=False, label="Upload original receipt or invoice (optional)",
        help_text="PDF, JPG, PNG or WebP, up to 10 MB. You can add another document later.")
    remember = forms.BooleanField(required=False, label="Remember this expense category for this merchant (suggest only)")

    payment_card = forms.ModelChoiceField(queryset=Account.objects.none(), required=False, label="Credit card being paid")
    payment_funding = forms.ChoiceField(required=False, choices=[("", "Choose funding source"),
        ("personal", "Personal funds — Owner Investment"), ("business", "Business bank funds")])
    payment_equity = forms.ModelChoiceField(queryset=Account.objects.none(), required=False, label="Owner Investment account")
    payment_business = forms.DecimalField(required=False, min_value=Decimal("0.01"), max_digits=14, decimal_places=2,
        label="Business liability portion of payment")

    def __init__(self, *args, row, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.fields["payment_card"].queryset = eligible_import_accounts().filter(account_type="liability")
        self.fields["payment_equity"].queryset = Account.objects.filter(is_active=True, account_type="equity", name__iregex=r"owner.*(investment|contribution)|capital contribution")
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["category"].queryset = Account.objects.filter(is_active=True, account_type__in=(
            "expense", "cogs", "other_expense", "income", "other_income"))
        self.category_types = {str(a.pk): a.account_type for a in self.fields["category"].queryset}
        self.documents = Receipt.objects.filter(source="bank_document",
            source_reference__startswith=f"{row.pk}:").order_by("pk")

    def clean_attachment(self):
        return ReceiptForm.clean_attachment(self)

    def clean(self):
        data = super().clean()
        kind = data.get("classification")
        if kind != "card_payment":
            for key in ("payment_card", "payment_funding", "payment_equity", "payment_business"):
                data[key] = None
        if kind == "personal":
            for key in ("vendor", "new_vendor", "category", "remember"):
                data[key] = None
        vendor, name, category = data.get("vendor"), data.get("new_vendor"), data.get("category")
        attachment = data.get("attachment")
        documents = list(self.documents)
        legacy = self.row.review_data.get("receipt")
        if legacy:
            documents += list(Receipt.objects.filter(pk=legacy))
        if documents and (kind not in ("expense", "split") or not vendor or any(d.vendor_id != vendor.pk for d in documents)):
            self.add_error("vendor", "Existing purchase documentation is linked to this vendor. Keep the vendor and expense classification.")
        if name and (vendor or Vendor.objects.filter(name__iexact=name).exists()):
            self.add_error("new_vendor", "Select the existing vendor instead.")
        if kind in ("expense", "split"):
            if self.row.amount >= 0:
                self.add_error("classification", "Use further review for credits or refunds.")
            if not vendor and not name:
                self.add_error("vendor", "Select or create a vendor.")
            if kind == "expense" and (not category or category.account_type not in ("expense", "cogs", "other_expense")):
                self.add_error("category", "Select an expense or cost of goods sold account.")
            if kind == "split" and (category or data.get("remember")):
                self.add_error("category", "Use the allocation categories below; do not remember a single category for a split.")

        elif kind == "card_payment":
            source = eligible_import_accounts().filter(pk=self.row.account_id, account_type="asset").first()
            if not source or self.row.amount >= 0:
                self.add_error("classification", "Review the outgoing bank payment only. Incoming card-side payments require matching later.")
            if not data.get("payment_card"):
                self.add_error("payment_card", "Select the card being paid.")
            funding = data.get("payment_funding")
            if funding not in ("personal", "business"):
                self.add_error("payment_funding", "Choose the funding source.")
            if funding == "personal" and not data.get("payment_equity"):
                self.add_error("payment_equity", "Select the Owner Investment equity account.")
            if funding == "business" and data.get("payment_equity"):
                self.add_error("payment_equity", "Business bank funding does not use Owner Investment.")
            portion = data.get("payment_business")
            if portion is None or portion > abs(self.row.amount):
                self.add_error("payment_business", "Enter a positive business portion no greater than the payment.")
            if vendor or name or category or attachment or data.get("remember"):
                self.add_error("classification", "A card payment is not a new purchase or expense. Clear purchase fields.")
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
    account_filter = request.GET.get("account_filter", "")
    if not (account_filter.isdecimal() and len(account_filter) <= 18):
        account_filter = ""
    back_url = reverse("accounting:import_inbox") + "?" + urlencode({"tab": "excluded" if request.GET.get("tab") == "excluded" else "review", "account_filter": account_filter})
    initial = dict(row.review_data)
    suggestion = ""
    # Do not silently upgrade an older exact-description authorization.
    if initial.get("remember") and initial.get("remember_scope") != "merchant":
        initial["remember"] = False
    if not initial:
        initial, suggestion = suggest(row)
    form = BankReviewForm(request.POST or None, request.FILES or None, row=row, initial=initial)
    split_initial = row.review_data.get("splits", [])
    split_formset = SplitFormSet(request.POST if request.method == "POST" and request.POST.get("classification") == "split" else None,
                                initial=split_initial, prefix="splits")
    valid = request.method == "POST" and form.is_valid()
    allocations = []
    if request.method == "POST" and request.POST.get("classification") == "split":
        allocations, error = validate_allocations(split_formset, row.amount)
        if error:
            form.add_error(None, error)
            valid = False
    if valid:
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
            "remember_scope": "merchant" if data.get("remember") else "",
            "reviewed_by": request.user.pk,
            "payment_card": data["payment_card"].pk if data.get("payment_card") else None,
            "payment_funding": data.get("payment_funding") or "",
            "payment_equity": data["payment_equity"].pk if data.get("payment_equity") else None,
            "payment_business": str(data["payment_business"]) if data.get("payment_business") is not None else None,
            "payment_remainder": str(abs(row.amount) - data["payment_business"]) if data.get("payment_business") is not None else None,
            "splits": allocations,
            "business_amount": str(sum((Decimal(line["amount"]) for line in allocations if line["kind"] == "business"), Decimal("0"))) if allocations else None,
            "personal_amount": str(sum((Decimal(line["amount"]) for line in allocations if line["kind"] == "personal"), Decimal("0"))) if allocations else None,
        }
        row.status = {"personal": ImportRow.EXCLUDED, "deferred": ImportRow.PENDING}.get(
            data["classification"], ImportRow.REVIEWED)
        row.save(update_fields=["review_data", "status"])
        return redirect(reverse("accounting:import_inbox") + "?" + urlencode({"tab": "review", "account_filter": account_filter}))
    account = Account.objects.filter(pk=row.account_id).first()
    return render(request, "accounting_imports/bank_review.html",
                  {"row": row, "account": account, "form": form,
                   "suggestion": suggestion, "back_url": back_url, "amount_label": ("−" if row.amount < 0 else "") + f"${abs(row.amount):,.2f}",
                   "split_formset": split_formset, "purchase_cents": int(abs(row.amount) * 100), "category_types": form.category_types, "documents": form.documents, "legacy_receipt": row.review_data.get("receipt")})
