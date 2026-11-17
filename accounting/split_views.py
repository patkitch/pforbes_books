"""Manual split transactions: one payment account and two to five categories."""
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import JournalEntry, JournalLine
from .services import post_entry
from accounting_contacts.models import TransactionParty
from accounting_contacts.services import link_contact
from .split_forms import SplitTransactionForm


def _save_lines(entry, details):
    """Caller must hold a transaction and lock the draft before changing lines."""
    kind = details["kind"]
    total = details["split_total"]
    payment = details["payment_account"]
    for category, amount in details["split_lines"]:
        JournalLine.objects.create(
            entry=entry, account=category,
            debit=amount if kind == "expense" else Decimal("0.00"),
            credit=amount if kind == "income" else Decimal("0.00"),
        )
    JournalLine.objects.create(
        entry=entry, account=payment,
        debit=total if kind == "income" else Decimal("0.00"),
        credit=total if kind == "expense" else Decimal("0.00"),
    )


@staff_member_required(login_url="/admin/login/")
def split_new(request):
    form = SplitTransactionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                date=d["date"], payee=d["payee"], description=d["description"],
                memo=d["memo"], source="manual_split", created_by=request.user,
            )
            _save_lines(entry, d)
            if d.get("vendor") or d.get("customer"):
                link_contact(entry, vendor=d.get("vendor"), customer=d.get("customer"), actor=request.user)
            if d["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/split_transaction_form.html", {"form": form})


@staff_member_required(login_url="/admin/login/")
def split_edit(request, pk):
    entry = get_object_or_404(JournalEntry.objects.prefetch_related("lines__account"), pk=pk)
    if entry.source != "manual_split" or entry.status != "draft":
        raise Http404("Only manual split drafts may be edited.")
    lines = list(entry.lines.all())
    payment_lines = [line for line in lines if line.account.account_type in ("asset", "liability")]
    category_lines = [line for line in lines if line.account.account_type not in ("asset", "liability")]
    if len(payment_lines) != 1 or not 2 <= len(category_lines) <= SplitTransactionForm.MAX_SPLITS:
        raise Http404("This entry cannot be edited with the split form.")
    payment_line = payment_lines[0]
    if payment_line.credit > 0:
        kind = "expense"
        amounts = [line.debit for line in category_lines]
        total = payment_line.credit
    elif payment_line.debit > 0:
        kind = "income"
        amounts = [line.credit for line in category_lines]
        total = payment_line.debit
    else:
        raise Http404("Invalid split payment line.")
    if any(amount <= 0 for amount in amounts) or sum(amounts, Decimal("0.00")) != total:
        raise Http404("Unbalanced split draft.")
    initial = {
        "kind": kind, "date": entry.date, "payee": entry.payee,
        "description": entry.description, "memo": entry.memo,
        "payment_account": payment_line.account_id, "save_action": "draft",
    }
    for index, (line, amount) in enumerate(zip(category_lines, amounts), start=1):
        initial[f"category_{index}"] = line.account_id
        initial[f"amount_{index}"] = amount
    party = TransactionParty.objects.filter(journal_entry_id=entry.pk).first()
    if party:
        initial["vendor"], initial["customer"] = party.vendor_id, party.customer_id
    form = SplitTransactionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            locked = JournalEntry.objects.select_for_update().get(pk=pk)
            if locked.status != "draft" or locked.source != "manual_split":
                return HttpResponseForbidden("This entry is no longer an editable split draft.")
            locked.date = d["date"]
            locked.payee = d["payee"]
            locked.description = d["description"]
            locked.memo = d["memo"]
            locked.save(update_fields=["date", "payee", "description", "memo"])
            locked.lines.all().delete()
            _save_lines(locked, d)
            if d.get("vendor") or d.get("customer"):
                link_contact(locked, vendor=d.get("vendor"), customer=d.get("customer"), actor=request.user)
            if d["save_action"] == "post":
                post_entry(locked.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/split_transaction_form.html", {"form": form, "entry": entry})
