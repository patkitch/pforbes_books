"""Separate owner contribution workflow; posted entries stay locked."""
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import JournalEntry, JournalLine
from .owner_forms import OwnerContributionForm
from .services import post_entry


def _save_owner_lines(entry, cleaned):
    JournalLine.objects.create(
        entry=entry, account=cleaned["destination_account"], debit=cleaned["amount"]
    )
    JournalLine.objects.create(
        entry=entry, account=cleaned["contribution_account"], credit=cleaned["amount"]
    )


@staff_member_required(login_url="/admin/login/")
def owner_new(request):
    form = OwnerContributionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                date=d["date"], payee=d["payee"], description=d["description"],
                memo=d["memo"], source="manual_owner", created_by=request.user
            )
            _save_owner_lines(entry, d)
            if d["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/owner_form.html", {"form": form})


@staff_member_required(login_url="/admin/login/")
def owner_edit(request, pk):
    entry = get_object_or_404(JournalEntry.objects.prefetch_related("lines__account"), pk=pk)
    if entry.source != "manual_owner" or entry.status != "draft":
        raise Http404("Only draft owner contributions can be edited.")
    lines = list(entry.lines.all())
    if len(lines) != 2:
        raise Http404("Owner contribution draft must have two lines.")
    credit = next((line for line in lines if line.credit > 0 and line.debit == 0), None)
    debit = next((line for line in lines if line.debit > 0 and line.credit == 0), None)
    if (
        not credit or not debit or credit.account.account_type != "equity"
        or debit.account.account_type not in ("asset", "cogs", "expense", "other_expense")
        or credit.credit != debit.debit
    ):
        raise Http404("This draft cannot be edited through the owner form.")
    initial = {
        "kind": "cash" if debit.account.account_type == "asset" else "personal_expense",
        "date": entry.date, "payee": entry.payee,
        "description": entry.description, "amount": debit.debit,
        "contribution_account": credit.account_id,
        "destination_account": debit.account_id,
        "memo": entry.memo, "save_action": "draft",
    }
    form = OwnerContributionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            locked = JournalEntry.objects.select_for_update().get(pk=pk)
            if locked.status != "draft" or locked.source != "manual_owner":
                return HttpResponseForbidden("This owner contribution is no longer an editable draft.")
            locked.date = d["date"]
            locked.payee = d["payee"]
            locked.description = d["description"]
            locked.memo = d["memo"]
            locked.save(update_fields=["date", "payee", "description", "memo"])
            locked.lines.all().delete()
            _save_owner_lines(locked, d)
            if d["save_action"] == "post":
                post_entry(locked.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/owner_form.html", {"form": form, "entry": entry})
