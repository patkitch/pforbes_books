from collections import defaultdict

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import AccountForm
from .models import Account


@staff_member_required(login_url="/admin/login/")
def chart_of_accounts(request):
    show_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    accounts = list(Account.objects.select_related("parent").order_by("number", "name"))
    if not show_inactive:
        accounts = [a for a in accounts if a.is_active]
    if search:
        query = search.casefold()
        accounts = [a for a in accounts if query in a.number.casefold() or query in a.name.casefold()]

    # Group accounts by their actual account type, not number prefixes.
    # Preserve each parent/subaccount hierarchy, even for filtered results.
    shown_ids = {account.pk for account in accounts}
    by_type = defaultdict(list)
    for account in accounts:
        by_type[account.account_type].append(account)
    sections = []
    for type_key, title in [
        ("asset", "Assets"),
        ("liability", "Liabilities"),
        ("equity", "Owner's Equity"),
        ("income", "Income"),
        ("cogs", "Cost of Goods Sold"),
        ("expense", "Operating Expenses"),
        ("other_income", "Other Income"),
        ("other_expense", "Other Expenses"),
    ]:
        group_accounts = by_type.get(type_key, [])
        if not group_accounts:
            continue
        children = defaultdict(list)
        for account in group_accounts:
            parent_id = account.parent_id if account.parent_id in shown_ids else None
            children[parent_id].append(account)
        ordered = []
        def walk(parent_id, depth=0):
            for account in children.get(parent_id, []):
                ordered.append({"account": account, "depth": depth})
                walk(account.pk, depth + 1)
        walk(None)
        sections.append({
            "key": type_key, "title": title,
            "rows": ordered, "count": len(group_accounts),
        })
    return render(request, "accounting/chart_of_accounts.html", {
        "sections": sections,
        "search": search,
        "show_inactive": show_inactive,
        "account_count": len(accounts),
    })

@staff_member_required(login_url="/admin/login/")
def account_form(request, pk=None):
    account = get_object_or_404(Account, pk=pk) if pk else None
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        return redirect("accounting:chart_of_accounts")
    return render(request, "accounting/account_form.html", {
        "form": form, "account": account,
    })


@staff_member_required(login_url="/admin/login/")
def account_status(request, pk):
    account = get_object_or_404(Account, pk=pk)
    if request.method != "POST":
        return HttpResponseForbidden("Changing account status requires POST.")
    with transaction.atomic():
        account = Account.objects.select_for_update().get(pk=pk)
        if account.is_active and account.children.filter(is_active=True).exists():
            return render(request, "accounting/account_status_error.html", {
                "message": "Deactivate child accounts before deactivating this parent."
            }, status=400)
        if not account.is_active and account.parent and not account.parent.is_active:
            return render(request, "accounting/account_status_error.html", {
                "message": "Reactivate the parent account first."
            }, status=400)
        account.is_active = not account.is_active
        account.save(update_fields=["is_active"])
    return redirect(reverse("accounting:chart_of_accounts") + "?inactive=1")


@staff_member_required(login_url="/admin/login/")
def transaction_list(request):
    from .models import JournalEntry
    from accounting_contacts.models import Receipt
    entries = list(JournalEntry.objects.prefetch_related("lines__account").order_by("-date", "-pk")[:100])
    receipt_map = defaultdict(list)
    for receipt in Receipt.objects.filter(
        journal_entry_id__in=[entry.pk for entry in entries]
    ).only("pk", "title", "journal_entry_id", "attachment"):
        receipt_map[receipt.journal_entry_id].append(receipt)
    for entry in entries:
        entry.linked_receipts = receipt_map[entry.pk]
    return render(request, "accounting/transaction_list.html", {"entries": entries})


@staff_member_required(login_url="/admin/login/")
def income_new(request):
    return _transaction_new(request, fixed_kind="income")


@staff_member_required(login_url="/admin/login/")
def expense_new(request):
    return _transaction_new(request, fixed_kind="expense")


@staff_member_required(login_url="/admin/login/")
def transaction_new(request):
    return _transaction_new(request)


def _transaction_new(request, fixed_kind=None):
    from django.core.exceptions import ValidationError
    from .models import JournalEntry, JournalLine
    from .services import post_entry
    from .transaction_forms import SimpleTransactionForm
    from accounting_contacts.services import link_contact

    if fixed_kind and request.method == "POST":
        submitted = request.POST.copy()
        submitted["kind"] = fixed_kind
    else:
        submitted = request.POST or None
    form = SimpleTransactionForm(submitted, initial={"kind": fixed_kind, "_guided_kind": True} if fixed_kind else None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                date=d["date"], payee=d["payee"], description=d["description"],
                memo=d["memo"], source="manual", created_by=request.user,
            )
            if d["kind"] == "expense":
                debit_account, credit_account = d["category_account"], d["payment_account"]
            else:
                debit_account, credit_account = d["payment_account"], d["category_account"]
            JournalLine.objects.create(entry=entry, account=debit_account, debit=d["amount"])
            JournalLine.objects.create(entry=entry, account=credit_account, credit=d["amount"])
            if d.get("vendor") or d.get("customer"):
                link_contact(entry, vendor=d.get("vendor"), customer=d.get("customer"), actor=request.user)
            if d["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/transaction_form.html", {
        "form": form, "fixed_kind": fixed_kind,
    })


@staff_member_required(login_url="/admin/login/")
def transaction_edit(request, pk):
    """Edit or post a manually entered two-line draft; never edit posted entries."""
    from django.core.exceptions import ValidationError
    from django.http import Http404
    from .models import JournalEntry, JournalLine
    from .services import post_entry
    from .transaction_forms import SimpleTransactionForm
    from accounting_contacts.services import link_contact

    entry = get_object_or_404(JournalEntry.objects.prefetch_related("lines__account"), pk=pk)
    lines = list(entry.lines.all())
    if entry.status != "draft" or entry.source != "manual" or len(lines) != 2:
        raise Http404("Only simple manual drafts may be edited.")
    debit_line = next((line for line in lines if line.debit > 0), None)
    credit_line = next((line for line in lines if line.credit > 0), None)
    if not debit_line or not credit_line or debit_line.debit != credit_line.credit:
        raise Http404("Draft needs a balanced two-line entry.")
    if debit_line.account.account_type in ("expense", "cogs", "other_expense"):
        kind, category, payment = "expense", debit_line.account, credit_line.account
    elif credit_line.account.account_type in ("income", "other_income"):
        kind, category, payment = "income", credit_line.account, debit_line.account
    else:
        raise Http404("This draft cannot be edited through the simple form.")

    initial = {
        "kind": kind, "date": entry.date, "payee": entry.payee,
        "description": entry.description, "amount": debit_line.debit,
        "category_account": category.pk, "payment_account": payment.pk,
        "memo": entry.memo, "save_action": "draft",
    }
    from accounting_contacts.models import TransactionParty
    party = TransactionParty.objects.filter(journal_entry_id=entry.pk).first()
    if party:
        initial["vendor"] = party.vendor_id
        initial["customer"] = party.customer_id
    form = SimpleTransactionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            locked = JournalEntry.objects.select_for_update().get(pk=pk)
            if locked.status != "draft":
                return HttpResponseForbidden("This transaction is no longer a draft.")
            # Save both sides atomically and keep the original journal entry ID.
            locked.date = d["date"]
            locked.payee = d["payee"]
            locked.description = d["description"]
            locked.memo = d["memo"]
            locked.save(update_fields=["date", "payee", "description", "memo"])
            locked.lines.all().delete()
            if d["kind"] == "expense":
                debit_account, credit_account = d["category_account"], d["payment_account"]
            else:
                debit_account, credit_account = d["payment_account"], d["category_account"]
            JournalLine.objects.create(entry=locked, account=debit_account, debit=d["amount"])
            JournalLine.objects.create(entry=locked, account=credit_account, credit=d["amount"])
            if d.get("vendor") or d.get("customer"):
                link_contact(locked, vendor=d.get("vendor"), customer=d.get("customer"), actor=request.user)
            if d["save_action"] == "post":
                post_entry(locked.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/transaction_form.html", {"form": form, "entry": entry})


@staff_member_required(login_url="/admin/login/")
def account_ledger(request, pk):
    """Posted-only general ledger for one account, chronological running balance.

    This is a direct-account register, not a consolidated parent/subaccount report.
    Draft entries cannot affect a ledger balance.
    """
    from decimal import Decimal
    from .models import JournalLine

    account = get_object_or_404(Account, pk=pk)
    normal_debit = account.normal_side == "debit"
    lines = (
        JournalLine.objects.filter(account=account, entry__status="posted")
        .select_related("entry")
        .order_by("entry__date", "entry_id", "pk")
    )
    running = Decimal("0.00")
    rows = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for line in lines:
        total_debits += line.debit
        total_credits += line.credit
        running += line.debit - line.credit if normal_debit else line.credit - line.debit
        rows.append({"line": line, "balance": running})
    return render(request, "accounting/account_ledger.html", {
        "account": account,
        "rows": rows,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "balance": running,
        "normal_side": "Debit" if normal_debit else "Credit",
    })
