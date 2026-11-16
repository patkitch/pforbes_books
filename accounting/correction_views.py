"""Auditable posted-entry reversal. Never rewrite or delete posted journal lines."""
from datetime import date

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import AuditEvent, JournalEntry, JournalLine
from .services import post_entry
from .period_controls import period_is_locked


class ReversalForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), initial=date(2027, 1, 1)
    )
    reason = forms.CharField(
        max_length=255, label="Reason for reversing the transaction"
    )

    def clean_date(self):
        value = self.cleaned_data["date"]
        if period_is_locked(value):
            raise forms.ValidationError("This accounting period is locked.")
        if value < date(2027, 1, 1):
            raise forms.ValidationError("This new ledger begins January 1, 2027.")
        return value


@staff_member_required(login_url="/admin/login/")
def reverse_transaction(request, pk):
    original = get_object_or_404(
        JournalEntry.objects.prefetch_related("lines__account"), pk=pk
    )
    if original.status != "posted":
        raise Http404("Only posted entries can be reversed.")
    if original.reversed_by_entry_id is not None or original.source == "manual_reversal":
        raise Http404("This entry has already been reversed or is a reversal.")
    form = ReversalForm(
        request.POST or None,
        initial={"date": max(date(2027, 1, 1), original.date)},
    )
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        if values["date"] < original.date:
            form.add_error("date", "A reversal cannot predate the original transaction.")
        else:
            with transaction.atomic():
                locked = JournalEntry.objects.select_for_update().get(pk=pk)
                if (
                    locked.status != "posted" or locked.reversed_by_entry_id is not None
                    or locked.source == "manual_reversal"
                ):
                    return HttpResponseForbidden("This entry is no longer eligible for reversal.")
                reversal = JournalEntry.objects.create(
                    date=values["date"], payee=locked.payee,
                    description=f"Reversal of #{locked.pk}: {locked.description}"[:255],
                    memo=values["reason"], source="manual_reversal",
                    source_reference=str(locked.pk), created_by=request.user,
                )
                for line in locked.lines.all():
                    JournalLine.objects.create(
                        entry=reversal, account_id=line.account_id,
                        debit=line.credit, credit=line.debit,
                        memo=line.memo,
                    )
                post_entry(reversal.pk, actor=request.user)
                locked.reversed_by_entry = reversal
                locked.save(update_fields=["reversed_by_entry"])
                AuditEvent.objects.create(
                    entry=locked, action="reversed", actor=request.user,
                    note=f"Reversal entry #{reversal.pk}: {values['reason']}",
                )
            return redirect("accounting:transaction_list")
    return render(request, "accounting/reversal_form.html", {
        "form": form, "entry": original,
    })
