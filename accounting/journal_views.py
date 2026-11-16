"""Advanced multi-line journal draft / post workflow."""
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .journal_forms import GeneralJournalForm
from .models import JournalEntry, JournalLine
from .services import post_entry


def _write_lines(entry, values):
    for account, debit, credit in values["journal_lines"]:
        JournalLine.objects.create(
            entry=entry, account=account, debit=debit, credit=credit
        )


@staff_member_required(login_url="/admin/login/")
def journal_new(request):
    form = GeneralJournalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            entry = JournalEntry.objects.create(
                date=data["date"], payee=data["payee"],
                description=data["description"], memo=data["memo"],
                source="manual_journal", created_by=request.user,
            )
            _write_lines(entry, data)
            if data["save_action"] == "post":
                post_entry(entry.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/journal_form.html", {"form": form})


@staff_member_required(login_url="/admin/login/")
def journal_edit(request, pk):
    entry = get_object_or_404(
        JournalEntry.objects.prefetch_related("lines__account"), pk=pk
    )
    if entry.source != "manual_journal" or entry.status != "draft":
        raise Http404("Only advanced manual journal drafts can be edited.")
    lines = list(entry.lines.all())
    if not 2 <= len(lines) <= GeneralJournalForm.MAX_LINES:
        raise Http404("This draft is not supported by the journal form.")
    initial = {
        "date": entry.date, "payee": entry.payee,
        "description": entry.description, "memo": entry.memo,
        "save_action": "draft",
    }
    for n, line in enumerate(lines, start=1):
        initial[f"account_{n}"] = line.account_id
        initial[f"debit_{n}"] = line.debit if line.debit > 0 else None
        initial[f"credit_{n}"] = line.credit if line.credit > 0 else None
    form = GeneralJournalForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            locked = JournalEntry.objects.select_for_update().get(pk=pk)
            if locked.source != "manual_journal" or locked.status != "draft":
                return HttpResponseForbidden("The journal entry is no longer editable.")
            locked.date = data["date"]
            locked.payee = data["payee"]
            locked.description = data["description"]
            locked.memo = data["memo"]
            locked.save(update_fields=["date", "payee", "description", "memo"])
            locked.lines.all().delete()
            _write_lines(locked, data)
            if data["save_action"] == "post":
                post_entry(locked.pk, actor=request.user)
        return redirect("accounting:transaction_list")
    return render(request, "accounting/journal_form.html", {"form": form, "entry": entry})
