"""Preview or import the approved QuickBooks COA mapping into a *local test* database.

Usage:
  python manage.py import_approved_coa "path/to/mapping.xlsx"
  python manage.py import_approved_coa "path/to/mapping.xlsx" --apply
The first command only previews; --apply may write to pforbes_books_accounting_test.
"""
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from accounting.models import Account

EXPECTED_DATABASE = "pforbes_books_accounting_test"
ACCOUNT_TYPE_MAP = {
    "Bank": "asset",
    "Accounts receivable (A/R)": "asset",
    "Other Current Assets": "asset",
    "Fixed Assets": "asset",
    "Accounts payable (A/P)": "liability",
    "Credit Card": "liability",
    "Other Current Liabilities": "liability",
    "Long Term Liabilities": "liability",
    "Equity": "equity",
    "Income": "income",
    "Cost of Goods Sold": "cogs",
    "Expenses": "expense",
    "Other Income": "other_income",
    "Other Expense": "other_expense",
}
PREFIX_TO_TYPE = {
    "1": "asset",
    "2": "liability",
    "3": "equity",
    "4": "income",
    "5": "cogs",
    "6": "expense",
    "7": "other_income",
    "8": "other_expense",
}


def read_mapping(path):
    # openpyxl is already installed through requirements.txt.
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "2027 COA Draft" not in workbook.sheetnames:
            raise CommandError("Workbook is missing the '2027 COA Draft' worksheet.")
        sheet = workbook["2027 COA Draft"]
        expected = [
            "Existing #", "QuickBooks account", "QB account type", "QB detail type",
            "Proposed 4-digit #", "Parent account",
        ]
        rows = sheet.iter_rows(values_only=True)
        header = list(next(rows, []))
        if header[:6] != expected:
            raise CommandError("The approved mapping columns do not match the expected format.")

        result = []
        for line_number, row in enumerate(rows, start=2):
            if not row or not row[1]:
                continue
            name = str(row[1]).strip()
            qb_type = str(row[2]).strip()
            if qb_type not in ACCOUNT_TYPE_MAP:
                raise CommandError(f"Row {line_number}: unknown QuickBooks type {qb_type!r}.")
            number = str(row[4]).strip()
            if not (len(number) == 4 and number.isascii() and number.isdigit()):
                raise CommandError(f"Row {line_number}: invalid account number {number!r}.")
            account_type = ACCOUNT_TYPE_MAP[qb_type]
            if PREFIX_TO_TYPE.get(number[0]) != account_type:
                raise CommandError(f"Row {line_number}: number/type mismatch for {name!r}.")
            parent = str(row[5]).strip() if row[5] else None
            result.append({
                "number": number,
                "name": name,
                "account_type": account_type,
                "detail_type": str(row[3]).strip() if row[3] else "",
                "parent": parent,
            })
    finally:
        workbook.close()

    names = [row["name"] for row in result]
    numbers = [row["number"] for row in result]
    if len(names) != len(set(names)) or len(numbers) != len(set(numbers)):
        raise CommandError("Mapping contains duplicate account names or numbers.")
    lookup = {row["name"]: row for row in result}
    for row in result:
        if row["parent"]:
            parent = lookup.get(row["parent"])
            if parent is None:
                raise CommandError(f"Missing parent {row['parent']!r} for {row['name']!r}.")
            if parent["account_type"] != row["account_type"]:
                raise CommandError(f"Parent type mismatch for {row['name']!r}.")
            if parent["parent"]:
                raise CommandError("Nested parents beyond one level require additional review.")
    return result


class Command(BaseCommand):
    help = "Preview or locally seed the approved 2027 Chart of Accounts."

    def add_arguments(self, parser):
        parser.add_argument("workbook", type=Path)
        parser.add_argument("--apply", action="store_true", help="Write only to the isolated accounting test database.")

    def handle(self, *args, **options):
        path = options["workbook"]
        if not path.is_file():
            raise CommandError(f"Mapping file not found: {path}")
        rows = read_mapping(path)
        if len(rows) != 155:
            raise CommandError(f"Expected 155 approved accounts, found {len(rows)}. Review before import.")
        totals = Counter(row["account_type"] for row in rows)
        self.stdout.write(f"Validated {len(rows)} unique accounts; {sum(bool(r['parent']) for r in rows)} subaccounts.")
        for account_type, count in sorted(totals.items()):
            self.stdout.write(f"  {account_type}: {count}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("PREVIEW ONLY. No database changes made."))
            return

        # The name check protects the real local inventory database, and blocks
        # use on production even if someone inadvertently copies the command there.
        if connection.settings_dict["NAME"] != EXPECTED_DATABASE:
            raise CommandError(
                f"REFUSING import: database must be {EXPECTED_DATABASE!r}; "
                f"currently configured as {connection.settings_dict['NAME']!r}."
            )
        if connection.vendor != "postgresql":
            raise CommandError("REFUSING import: --apply requires the isolated PostgreSQL test database.")
        if connection.settings_dict.get("HOST") not in ("127.0.0.1", "localhost"):
            raise CommandError("REFUSING import: database host must be local.")
        if Account.objects.exists():
            raise CommandError("REFUSING import: COA already contains accounts; no overwrite or duplicates allowed.")

        try:
            with transaction.atomic():
                created = {}
                # Parent accounts first so ForeignKey dependencies resolve.
                for row in sorted(rows, key=lambda item: bool(item["parent"])):
                    account = Account(
                        number=row["number"], name=row["name"],
                        account_type=row["account_type"], detail_type=row["detail_type"],
                        parent=created.get(row["parent"]),
                    )
                    account.full_clean()
                    account.save()
                    created[row["name"]] = account
        except ValidationError as exc:
            raise CommandError(f"Validation failed; transaction rolled back: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Imported {len(created)} accounts into local test database."))
