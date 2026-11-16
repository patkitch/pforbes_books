"""Draft/post manual money movements, with edit and correction support."""
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import AuditEvent, JournalEntry, JournalLine
from .money_forms import MoneyMovementForm, valid_account_types
from .services import post_entry


def _write_lines(entry, values):
    JournalLine.objects.create(
        entry=entry, account=values["debit_account"], debit=values["amount"]
    )
    JournalLine.objects.create(
        entry=entry, account=values["credit_account"], credit=values["amount"]
    )


def _infer_kind(debit, credit):
    # Owner draws use equity debit; card payments use liability debit.
    if debit.account_type == "equity" and credit.account_type == "asset":
        return "owner_draw"
    if debit.account_type == "liability" and credit.account_type == "asset":
        return "card_payment"
    if debit.account_type == "asset" and credit.account_type == "asset":
        return "transfer"
    if debit.account_type in ("asset", "liability") and credit.account_type in ("cogs", "expense", "other_expense"):
        return "purchase_refund"
    if debit.account_type in ("income", "other_income") and credit.account_type in ("asset", "liability"):
        return "sales_refund"
    return None


@staff_member_required(login_url="/admin/login/")
def movement_new(request):
    form = MoneyMovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                date=values["date"], payee=values["payee"],
                description=values["description"], memo=values["memo"],
                source="manual_movement", created_by=request.user,
            )
            _write_lines(entry, values)
            if values["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/movement_form.html", {"form": form})


@staff_member_required(login_url="/admin/login/")
def movement_edit(request, pk):
    entry = get_object_or_404(
        JournalEntry.objects.prefetch_related("lines__account"), pk=pk
    )
    if entry.source != "manual_movement" or entry.status != "draft":
        raise Http404("Only draft manual movements can be edited.")
    lines = list(entry.lines.all())
    if len(lines) != 2:
        raise Http404("This transaction needs exactly two lines.")
    debit = next((line for line in lines if line.debit > 0 and line.credit == 0), None)
    credit = next((line for line in lines if line.credit > 0 and line.debit == 0), None)
    if not debit or not credit or debit.debit != credit.credit:
        raise Http404("Unbalanced draft.")
    kind = _infer_kind(debit.account, credit.account)
    if kind is None:
        raise Http404("Unsupported movement type.")
    initial = {
        "kind": kind, "date": entry.date, "payee": entry.payee,
        "description": entry.description, "amount": debit.debit,
        "debit_account": debit.account_id, "credit_account": credit.account_id,
        "memo": entry.memo, "save_action": "draft",
    }
    form = MoneyMovementForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        with transaction.atomic():
            locked = JournalEntry.objects.select_for_update().get(pk=pk)
            if locked.status != "draft" or locked.source != "manual_movement":
                return HttpResponseForbidden("This movement is no longer an editable draft.")
            locked.date = values["date"]
            locked.payee = values["payee"]
            locked.description = values["description"]
            locked.memo = values["memo"]
            locked.save(update_fields=["date", "payee", "description", "memo"])
            locked.lines.all().delete()
            _write_lines(locked, values)
            if values["save_action"] == "post":
                post_entry(locked.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/movement_form.html", {"form": form, "entry": entry})
