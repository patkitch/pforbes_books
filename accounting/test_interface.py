"""User interface navigation and guided-entry regression checks."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry
from .reporting import profit_and_loss


class AccountingInterfaceTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="interface_tester", password="pass", is_staff=True)
        self.client.force_login(user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.sales = Account.objects.create(number="4001", name="Artwork Sales", account_type="income")
        self.expense = Account.objects.create(number="5004", name="Art Supplies", account_type="cogs")

    def test_dashboard_and_reports_page_have_working_links(self):
        dash = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(dash.status_code, 200)
        self.assertContains(dash, "Accounting Dashboard")
        self.assertContains(dash, "Year to Date")
        self.assertContains(dash, reverse("accounting:income_new"))
        self.assertContains(dash, reverse("accounting:expense_new"))
        self.assertContains(dash, reverse("accounting:reports_index"))
        reports = self.client.get(reverse("accounting:reports_index"))
        self.assertEqual(reports.status_code, 200)
        for label in ("Profit &amp; Loss", "Balance Sheet", "Trial Balance"):
            self.assertContains(reports, label)

    def test_dashboard_values_use_posted_entries_only(self):
        for amount, status in (("250.00", "posted"), ("50.00", "draft")):
            entry = JournalEntry.objects.create(
                date=date(2027, 1, 15), description="Test artwork", status=status
            )
            from .models import JournalLine
            JournalLine.objects.create(entry=entry, account=self.bank, debit=Decimal(amount))
            JournalLine.objects.create(entry=entry, account=self.sales, credit=Decimal(amount))
        dash = self.client.get(reverse("accounting:dashboard"))
        self.assertContains(dash, "&#36;250.00")
        self.assertNotContains(dash, "$300.00")

    def test_guided_income_and_expense_forms_filter_categories(self):
        income = self.client.get(reverse("accounting:income_new"))
        self.assertContains(income, "Record Income")
        self.assertContains(income, "Artwork Sales")
        self.assertNotContains(income, 'Art Supplies</option>')
        expense = self.client.get(reverse("accounting:expense_new"))
        self.assertContains(expense, "Record Expense")
        self.assertContains(expense, "Art Supplies")
        self.assertNotContains(expense, 'Artwork Sales</option>')

    def test_guided_forms_have_distinct_labels_and_contact_links(self):
        income = self.client.get(reverse("accounting:income_new"))
        self.assertContains(income, "Received From (optional name)")
        self.assertContains(income, "Income Category")
        self.assertContains(income, "Deposit To Account")
        self.assertContains(income, "+ Create customer")
        self.assertNotContains(income, "+ Create vendor")

        expense = self.client.get(reverse("accounting:expense_new"))
        self.assertContains(expense, "Paid To (optional name)")
        self.assertContains(expense, "Expense Category")
        self.assertContains(expense, "Paid From Account")
        self.assertContains(expense, "+ Create vendor")
        self.assertNotContains(expense, "+ Create customer")

    def test_income_route_cannot_be_tricked_into_posting_expense(self):
        data = {
            "kind": "expense", "date": "2027-01-19",
            "description": "Customer artwork", "amount": "75.00",
            "category_account": str(self.sales.pk),
            "payment_account": str(self.bank.pk), "save_action": "post",
        }
        result = self.client.post(reverse("accounting:income_new"), data)
        self.assertEqual(result.status_code, 302)
        entry = JournalEntry.objects.get(description="Customer artwork")
        self.assertEqual(entry.lines.get(account=self.sales).credit, Decimal("75.00"))
        self.assertEqual(
            profit_and_loss(date(2027, 1, 1), date(2027, 12, 31))["totals"]["income"],
            Decimal("75.00"),
        )

    def test_journal_shows_add_line_button_and_keeps_eight_fields_for_post(self):
        result = self.client.get(reverse("accounting:journal_new"))
        self.assertContains(result, "Add Line")
        self.assertContains(result, 'data-journal-row="8"')
        self.assertContains(result, 'id="total-debits"')

    def test_chart_sections_are_grouped_and_preserve_subaccounts(self):
        parent = Account.objects.create(
            number="5001", name="Cost of sales", account_type="cogs"
        )
        self.expense.parent = parent
        self.expense.save(update_fields=["parent"])
        Account.objects.create(
            number="2001", name="Credit Card", account_type="liability"
        )
        result = self.client.get(reverse("accounting:chart_of_accounts"))
        self.assertEqual(result.status_code, 200)
        for section in ("Assets", "Liabilities", "Income", "Cost of Goods Sold"):
            self.assertContains(result, section)
        self.assertContains(result, "child-row")
        self.assertContains(result, "Collapse subaccounts")
        body = result.content.decode()
        self.assertLess(body.index("Assets"), body.index("Liabilities"))
        self.assertLess(body.index("Liabilities"), body.index("Cost of Goods Sold"))
        self.assertLess(body.index("Cost of sales"), body.index("Art Supplies"))
        self.assertContains(
            self.client.get(reverse("accounting:chart_of_accounts"), {"q": "Art Supplies"}),
            "Cost of Goods Sold",
        )

    def test_2026_income_and_expense_can_post_and_are_reported_by_year(self):
        for kind, account, name in (
            ("income", self.sales, "2026 sale"),
            ("expense", self.expense, "2026 supplies"),
        ):
            response = self.client.post(reverse("accounting:transaction_new"), {
                "kind": kind, "date": "2026-09-14", "description": name,
                "amount": "30.00", "category_account": str(account.pk),
                "payment_account": str(self.bank.pk), "save_action": "post",
            })
            self.assertEqual(response.status_code, 302)
        report = profit_and_loss(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(report["totals"]["income"], Decimal("30.00"))
        self.assertEqual(report["totals"]["cogs"], Decimal("30.00"))
        self.assertEqual(report["net_profit"], Decimal("0.00"))
        response = self.client.get(
            reverse("accounting:profit_loss"),
            {"start": "2026-01-01", "end": "2026-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026")

    def test_2025_dates_still_rejected(self):
        response = self.client.post(reverse("accounting:income_new"), {
            "date": "2025-12-31", "description": "Too early",
            "amount": "10.00", "category_account": str(self.sales.pk),
            "payment_account": str(self.bank.pk), "save_action": "post",
        })
        self.assertContains(response, "begins January 1, 2026")
        self.assertFalse(JournalEntry.objects.exists())

    def test_accounting_routes_require_staff_login(self):
        self.client.logout()
        for name in ("dashboard", "reports_index", "income_new", "expense_new"):
            response = self.client.get(reverse("accounting:" + name))
            self.assertEqual(response.status_code, 302)
