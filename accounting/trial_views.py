"""Trial balance screen and CSV download, using the same validated date."""
import csv

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render

from .report_views import BalanceSheetDate, default_balance_sheet_date
from .trial_reporting import trial_balance


def _validated(request):
    form = BalanceSheetDate(request.GET if request.GET else default_balance_sheet_date())
    return form, trial_balance(form.cleaned_data["as_of"]) if form.is_valid() else None


@staff_member_required(login_url="/admin/login/")
def trial_balance_view(request):
    form, report = _validated(request)
    return render(
        request, "accounting/trial_balance.html",
        {"form": form, "report": report},
    )


@staff_member_required(login_url="/admin/login/")
def trial_balance_csv(request):
    form, report = _validated(request)
    if report is None:
        return HttpResponse("Invalid report date.", status=400)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="trial_balance_{report["as_of"]}.csv"'
    )
    response["Cache-Control"] = "no-store"
    writer = csv.writer(response)
    writer.writerow(["P. Forbes Art Trial Balance", f"As of {report['as_of']}"])
    writer.writerow(["Account number", "Account name", "Debit", "Credit"])
    for row in report["rows"]:
        account = row["account"]
        writer.writerow([
            account.number, account.name,
            f'{row["debit"]:.2f}', f'{row["credit"]:.2f}',
        ])
    writer.writerow(["", "Total", f'{report["debits"]:.2f}', f'{report["credits"]:.2f}'])
    writer.writerow(["", "Difference", f'{report["difference"]:.2f}', ""])
    return response
