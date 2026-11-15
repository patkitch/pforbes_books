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

    # For search results retain each match even if its parent is hidden.
    children = defaultdict(list)
    for account in accounts:
        parent_id = account.parent_id if account.parent_id in {x.pk for x in accounts} else None
        children[parent_id].append(account)
    ordered = []
    def walk(parent_id, depth=0):
        for account in children.get(parent_id, []):
            ordered.append({"account": account, "depth": depth})
            walk(account.pk, depth + 1)
    walk(None)
    return render(request, "accounting/chart_of_accounts.html", {
        "rows": ordered,
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
    entries = JournalEntry.objects.prefetch_related("lines__account").order_by("-date", "-pk")[:100]
    return render(request, "accounting/transaction_list.html", {"entries": entries})


@staff_member_required(login_url="/admin/login/")
def transaction_new(request):
    from django.core.exceptions import ValidationError
    from .models import JournalEntry, JournalLine
    from .services import post_entry
    from .transaction_forms import SimpleTransactionForm

    form = SimpleTransactionForm(request.POST or None)
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
            if d["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/transaction_form.html", {"form": form})
