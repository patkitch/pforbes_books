"""Staff-only contact directory, transaction linking, and receipt handling."""
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from decimal import Decimal
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounting.models import AuditEvent, JournalEntry, JournalLine
from .forms import ArtworkItemFormSet, CustomerForm, ReceiptForm, TransactionPartyForm, VendorForm
from .models import Customer, Receipt, ReceiptItem, TransactionParty, Vendor
from .services import link_contact


@staff_member_required(login_url="/admin/login/")
def vendors(request):
    query = request.GET.get("q", "").strip()
    records = Vendor.objects.all()
    if query:
        records = records.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
        )
    return render(request, "accounting_contacts/list.html", {
        "records": records[:300], "kind": "vendors",
        "title": "Vendors", "query": query,
    })


@staff_member_required(login_url="/admin/login/")
def customers(request):
    query = request.GET.get("q", "").strip()
    records = Customer.objects.all()
    if query:
        records = records.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
        )
    return render(request, "accounting_contacts/list.html", {
        "records": records[:300], "kind": "customers",
        "title": "Customers", "query": query,
    })


@staff_member_required(login_url="/admin/login/")
def vendor_edit(request, pk=None):
    obj = get_object_or_404(Vendor, pk=pk) if pk else None
    form = VendorForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        return redirect("accounting:vendor_detail", pk=obj.pk)
    return render(request, "accounting_contacts/form.html", {
        "title": "Edit vendor" if obj else "Add vendor",
        "form": form, "back": reverse("accounting:vendors"),
    })


@staff_member_required(login_url="/admin/login/")
def customer_edit(request, pk=None):
    obj = get_object_or_404(Customer, pk=pk) if pk else None
    form = CustomerForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        return redirect("accounting:customer_detail", pk=obj.pk)
    return render(request, "accounting_contacts/form.html", {
        "title": "Edit customer" if obj else "Add customer",
        "form": form, "back": reverse("accounting:customers"),
    })


def _linked_entries(record, key):
    ids = TransactionParty.objects.filter(**{key: record}).values_list("journal_entry_id", flat=True)
    return JournalEntry.objects.filter(pk__in=ids).prefetch_related("lines__account").order_by("-date", "-pk")


@staff_member_required(login_url="/admin/login/")
def vendor_detail(request, pk):
    record = get_object_or_404(Vendor, pk=pk)
    entries = list(_linked_entries(record, "vendor"))
    receipts = Receipt.objects.filter(vendor=record)
    posted_ids = [entry.pk for entry in entries if entry.status == "posted"]
    lines = JournalLine.objects.filter(
        entry_id__in=posted_ids,
        account__account_type__in=("expense", "cogs", "other_expense"),
    )
    activity_total = sum((line.debit - line.credit for line in lines), Decimal("0.00"))
    return render(request, "accounting_contacts/detail.html", {
        "title": "Vendor", "record": record, "kind": "vendor",
        "activity_total": activity_total, "entries": entries, "receipts": receipts,
        "edit_url": reverse("accounting:vendor_edit", args=[record.pk]),
        "list_url": reverse("accounting:vendors"),
        "receipt_url": reverse("accounting:receipt_new") + f"?vendor={record.pk}",
    })


@staff_member_required(login_url="/admin/login/")
def customer_detail(request, pk):
    record = get_object_or_404(Customer, pk=pk)
    entries = list(_linked_entries(record, "customer"))
    receipts = Receipt.objects.filter(customer=record)
    posted_ids = [entry.pk for entry in entries if entry.status == "posted"]
    lines = JournalLine.objects.filter(
        entry_id__in=posted_ids,
        account__account_type__in=("income", "other_income"),
    )
    activity_total = sum((line.credit - line.debit for line in lines), Decimal("0.00"))
    return render(request, "accounting_contacts/detail.html", {
        "title": "Customer", "record": record, "kind": "customer",
        "activity_total": activity_total, "entries": entries, "receipts": receipts,
        "edit_url": reverse("accounting:customer_edit", args=[record.pk]),
        "list_url": reverse("accounting:customers"),
        "receipt_url": reverse("accounting:receipt_new") + f"?customer={record.pk}",
    })


@staff_member_required(login_url="/admin/login/")
def party_link(request, pk):
    entry = get_object_or_404(JournalEntry, pk=pk)
    current = TransactionParty.objects.filter(journal_entry_id=entry.pk).first()
    initial = {}
    if current:
        initial = {
            "party_type": "vendor" if current.vendor_id else "customer",
            "vendor": current.vendor_id, "customer": current.customer_id,
        }
    form = TransactionPartyForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        vendor = data["vendor"] if data["party_type"] == "vendor" else None
        customer = data["customer"] if data["party_type"] == "customer" else None
        link_contact(entry, vendor=vendor, customer=customer, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting_contacts/link.html", {
        "entry": entry, "form": form, "linked": current,
    })


@staff_member_required(login_url="/admin/login/")
def receipts(request):
    query = request.GET.get("q", "").strip()
    records = Receipt.objects.select_related("vendor", "customer").all()
    if query:
        records = records.filter(
            Q(title__icontains=query) | Q(source_reference__icontains=query)
            | Q(vendor__name__icontains=query) | Q(customer__name__icontains=query)
        )
    return render(request, "accounting_contacts/receipt_list.html", {
        "records": records[:300], "query": query,
    })


@staff_member_required(login_url="/admin/login/")
def receipt_edit(request, pk=None):
    receipt = get_object_or_404(Receipt, pk=pk) if pk else None
    initial = {}
    if request.method != "POST" and not receipt:
        if request.GET.get("vendor", "").isdigit():
            initial["vendor"] = request.GET["vendor"]
            initial["receipt_type"] = "purchase"
        if request.GET.get("customer", "").isdigit():
            initial["customer"] = request.GET["customer"]
            initial["receipt_type"] = "sale"
        if request.GET.get("transaction", "").isdigit():
            entry = get_object_or_404(JournalEntry, pk=request.GET["transaction"])
            initial["journal_entry_id"] = entry.pk
    form = ReceiptForm(request.POST or None, request.FILES or None, instance=receipt, initial=initial)
    existing_items = []
    if receipt:
        existing_items = [
            {
                "artwork_title": item.artwork_title, "item_type": item.item_type,
                "size": item.size, "quantity": item.quantity, "unit_price": item.unit_price,
            }
            for item in receipt.items.all()
        ]
    has_item_post = request.method == "POST" and "items-TOTAL_FORMS" in request.POST
    items = ArtworkItemFormSet(
        data=request.POST if has_item_post else None,
        initial=existing_items if not has_item_post else None,
        prefix="items",
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if has_item_post and not items.is_valid():
            form.add_error(None, "Please correct the artwork item rows.")
        if has_item_post and items.is_valid():
            entered = [
                line for line in items.cleaned_data
                if line and line.get("artwork_title")
            ]
            if obj.receipt_type != "sale" and entered:
                form.add_error(None, "Artwork line items belong on sales receipts only.")
            if obj.receipt_type == "sale" and entered:
                subtotal = sum(
                    (line["quantity"] * line["unit_price"] for line in entered),
                    Decimal("0.00"),
                )
                if subtotal > obj.amount:
                    form.add_error(
                        "amount",
                        "Artwork item subtotal exceeds receipt amount. "
                        "Check prices, quantities, or the receipt total.",
                    )
        if obj.journal_entry_id and (obj.vendor_id or obj.customer_id):
            existing = TransactionParty.objects.filter(journal_entry_id=obj.journal_entry_id).first()
            if existing and (
                existing.vendor_id != obj.vendor_id or existing.customer_id != obj.customer_id
            ):
                form.add_error(
                    "journal_entry_id",
                    "This journal transaction is already linked to a different contact. Review its contact link first.",
                )
        if not form.errors:
            with transaction.atomic():
                obj.save()
                if has_item_post:
                    obj.items.all().delete()
                    if obj.receipt_type == "sale":
                        ReceiptItem.objects.bulk_create([
                            ReceiptItem(
                                receipt=obj, position=position,
                                artwork_title=line["artwork_title"],
                                item_type=line["item_type"],
                                size=line.get("size") or "",
                                quantity=line["quantity"],
                                unit_price=line["unit_price"],
                            )
                            for position, line in enumerate(entered, start=1)
                        ])
                if obj.journal_entry_id and (obj.vendor_id or obj.customer_id):
                    entry = JournalEntry.objects.get(pk=obj.journal_entry_id)
                    existing = TransactionParty.objects.filter(journal_entry_id=entry.pk).first()
                    if existing is None:
                        link_contact(entry, vendor=obj.vendor, customer=obj.customer, actor=request.user)
            return redirect("accounting:receipt_detail", pk=obj.pk)
    return render(request, "accounting_contacts/form.html", {
        "title": "Edit receipt" if receipt else "Add receipt",
        "form": form, "back": reverse("accounting:receipts"),
        "has_file": True, "items": items,
    })

@staff_member_required(login_url="/admin/login/")
def receipt_detail(request, pk):
    receipt = get_object_or_404(
        Receipt.objects.select_related("vendor", "customer"), pk=pk
    )
    return render(request, "accounting_contacts/receipt_detail.html", {
        "receipt": receipt,
    })


@staff_member_required(login_url="/admin/login/")
def receipt_download(request, pk):
    receipt = get_object_or_404(Receipt, pk=pk)
    if not receipt.attachment:
        raise Http404("No document attached.")
    try:
        handle = receipt.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Document file is not available.")
    response = FileResponse(
        handle, as_attachment=True, filename=receipt.attachment.name.rsplit("/", 1)[-1]
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
