"""Read-only CSV preview for bank and credit-card imports.

No transactions, contacts or journal lines are written by this module.
Import acceptance, vendor matching, and owner-funded card payments are
separate future workflows requiring explicit user review.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import Account


MAX_BYTES = 1_000_000
MAX_ROWS = 1000
REQUIRED = {"date", "description"}
AMOUNT_SCHEMAS = ({"amount"}, {"debit", "credit"})


class ImportPreviewForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        label="Account whose statement you are previewing",
        help_text="Select a business bank or credit card account. Nothing will be posted.",
    )
    file = forms.FileField(
        label="Bank or credit card CSV file",
        help_text="Columns: Date, Description, Amount; or Date, Description, Debit, Credit. CSV only, up to 1 MB and 1,000 transactions.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(
            is_active=True, account_type__in=("asset", "liability")
        ).order_by("number")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".csv"):
            raise forms.ValidationError("Choose a CSV file.")
        if upload.size > MAX_BYTES:
            raise forms.ValidationError("CSV file must be no more than 1 MB.")
        return upload


def _parse_amount(raw, row_number):
    clean = str(raw or "").strip().replace(",", "")
    if clean.startswith("$"):
        clean = clean[1:]
    if clean.startswith("(") and clean.endswith(")"):
        clean = "-" + clean[1:-1]
    try:
        value = Decimal(clean)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Row {row_number}: invalid amount.") from exc
    if not value.is_finite() or value.as_tuple().exponent < -2:
        raise ValueError(f"Row {row_number}: amount must be a finite number with no more than two decimal places.")
    return value


def parse_csv_preview(raw):
    """Parse CSV into rows, without touching the database."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be saved as UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV is missing column headers.")
    normalized = [str(name or "").strip().casefold() for name in reader.fieldnames]
    if len(normalized) != len(set(normalized)):
        raise ValueError("CSV has duplicate column names.")
    headers = set(normalized)
    if not REQUIRED.issubset(headers) or not any(schema.issubset(headers) for schema in AMOUNT_SCHEMAS):
        raise ValueError("CSV needs Date and Description, plus Amount or Debit and Credit columns.")
    if "amount" in headers and ("debit" in headers or "credit" in headers):
        raise ValueError("Use Amount OR Debit and Credit columns, not both.")
    parsed = []
    for line, row in enumerate(reader, start=2):
        if len(parsed) >= MAX_ROWS:
            raise ValueError(f"CSV exceeds {MAX_ROWS} transactions.")
        if None in row:
            raise ValueError(f"Row {line} has too many columns.")
        record = {str(key).strip().casefold(): str(value or "").strip() for key, value in row.items()}
        when = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                when = datetime.strptime(record["date"], fmt).date()
                break
            except ValueError:
                continue
        if when is None:
            raise ValueError(f"Row {line}: date must be YYYY-MM-DD or MM/DD/YYYY.")
        description = record["description"]
        if not description:
            raise ValueError(f"Row {line}: description cannot be blank.")
        if "amount" in headers:
            amount = _parse_amount(record.get("amount"), line)
        else:
            debit = _parse_amount(record.get("debit") or "0", line)
            credit = _parse_amount(record.get("credit") or "0", line)
            if debit < 0 or credit < 0:
                raise ValueError(f"Row {line}: Debit and Credit columns must be nonnegative.")
            if debit and credit:
                raise ValueError(f"Row {line}: choose either a debit or a credit.")
            # This is a raw source-file display convention, NOT a statement
            # about accounting journal debit/credit orientation.
            amount = credit - debit
        parsed.append({
            "date": when, "description": description[:255],
            "amount": amount, "raw": record,
        })
    if not parsed:
        raise ValueError("CSV contains no transactions.")
    return parsed


@staff_member_required(login_url="/admin/login/")
def preview(request):
    form = ImportPreviewForm(request.POST or None, request.FILES or None)
    rows = None
    if request.method == "POST" and form.is_valid():
        try:
            rows = parse_csv_preview(form.cleaned_data["file"].read())
        except ValueError as exc:
            form.add_error("file", str(exc))
    return render(request, "accounting/import_preview.html", {
        "form": form, "rows": rows,
    })
