"""Staff-only staged CSV inbox. No approval or journal posting yet."""
from collections import Counter
from hashlib import sha256

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounting.import_preview import ImportPreviewForm, parse_csv_preview
from accounting.models import Account
from .models import ImportBatch, ImportRow


def _fingerprint(row):
    value = "|".join((
        row["date"].isoformat(),
        row["description"].strip().casefold(),
        f'{row["amount"]:.2f}',
    ))
    return sha256(value.encode("utf-8")).hexdigest()


@transaction.atomic
def stage_rows(account, filename, rows, actor=None):
    """Deduplicate per account while retaining legitimate identical rows in one statement."""
    batch = ImportBatch.objects.create(
        account_id=account.pk, filename=filename[:255], created_by=actor,
    )
    occurrences = Counter()
    added = skipped = 0
    for row in rows:
        fingerprint = _fingerprint(row)
        occurrences[fingerprint] += 1
        _, created = ImportRow.objects.get_or_create(
            account_id=account.pk,
            fingerprint=fingerprint,
            occurrence=occurrences[fingerprint],
            defaults={
                "batch": batch,
                "transaction_date": row["date"],
                "description": row["description"],
                "amount": row["amount"],
            },
        )
        if created:
            added += 1
        else:
            skipped += 1
    return batch, added, skipped


@staff_member_required(login_url="/admin/login/")
def inbox(request):
    form = ImportPreviewForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            rows = parse_csv_preview(upload.read())
        except ValueError as exc:
            form.add_error("file", str(exc))
        else:
            _, added, skipped = stage_rows(
                form.cleaned_data["account"], upload.name, rows, request.user
            )
            result = {"added": added, "skipped": skipped}
            form = ImportPreviewForm()
    accounts = Account.objects.filter(pk__in=ImportRow.objects.values("account_id"))
    names = {account.pk: str(account) for account in accounts}
    items = list(ImportRow.objects.select_related("batch").order_by("-transaction_date", "-pk")[:250])
    for item in items:
        item.account_label = names.get(item.account_id, f"Account #{item.account_id}")
    return render(request, "accounting_imports/inbox.html", {
        "form": form, "result": result, "items": items,
    })


@require_POST
@staff_member_required(login_url="/admin/login/")
def change_status(request, pk):
    row = get_object_or_404(ImportRow, pk=pk)
    target = request.POST.get("status")
    if target not in (ImportRow.PENDING, ImportRow.EXCLUDED):
        return HttpResponseBadRequest("Invalid status.")
    row.status = target
    row.save(update_fields=["status"])
    return redirect("accounting:import_inbox")
