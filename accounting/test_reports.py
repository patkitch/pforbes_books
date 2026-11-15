from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine
from .reporting import balance_sheet, profit_and_loss


class FinancialReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="financial_reports_test", password="test-password", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.visa = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.cogs_parent = Account.objects.create(number="5001", name="COGS", account_type="cogs")
        self.supplies = Account.objects.create(
            number="5004", name="Supplies", account_type="cogs", parent=self.cogs_parent
        )
        self.shipping = Account.objects.create(number="5006", name="Shipping", account_type="cogs")
        self.advertising = Account.objects.create(number="6100", name="Advertising", account_type="expense")
        self.equity = Account.objects.create(number="3100", name="Owner contribution", account_type="equity")

    def entry(self, day, lines, *, status="posted"):
        e = JournalEntry.objects.create(date=date(2027, 1, day), description="Report test", status=status)
        for account, debit, credit in lines:
            JournalLine.objects.create(
                entry=e, account=account,
                debit=Decimal(debit), credit=Decimal(credit),
            )
        return e

    def test_existing_credit_card_purchases(self):
        self.entry(1, [(self.supplies, "45.50", "0"), (self.visa, "0", "45.50")])
        self.entry(5, [
            (self.supplies, "60.00", "0"),
            (self.shipping, "40.00", "0"),
            (self.visa, "0", "100.00"),
        ])
        pl = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        bs = balance_sheet(date(2027, 1, 31))
        self.assertEqual(pl["totals"]["cogs"], Decimal("145.50"))
        self.assertEqual(pl["net_profit"], Decimal("-145.50"))
        self.assertEqual(bs["totals"]["liability"], Decimal("145.50"))
        self.assertEqual(bs["earnings"], Decimal("-145.50"))
        self.assertEqual(bs["total_equity"], Decimal("-145.50"))
        self.assertEqual(bs["difference"], Decimal("0.00"))
        self.assertTrue(bs["balanced"])
        # Posting to a child is counted once, even when a parent exists.
        self.assertEqual(len([row for group in pl["groups"] for row in group["rows"] if row["account"].pk == self.supplies.pk]), 1)

    def test_income_and_owner_contribution(self):
        self.entry(2, [(self.bank, "200.00", "0"), (self.sales, "0", "200.00")])
        self.entry(3, [(self.bank, "50.00", "0"), (self.equity, "0", "50.00")])
        pl = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        bs = balance_sheet(date(2027, 1, 31))
        self.assertEqual(pl["net_profit"], Decimal("200.00"))
        self.assertEqual(bs["totals"]["asset"], Decimal("250.00"))
        self.assertEqual(bs["totals"]["equity"], Decimal("50.00"))
        self.assertEqual(bs["total_equity"], Decimal("250.00"))
        self.assertTrue(bs["balanced"])

    def test_drafts_are_excluded(self):
        self.entry(2, [(self.bank, "100.00", "0"), (self.sales, "0", "100.00")], status="draft")
        self.assertEqual(profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))["net_profit"], Decimal("0.00"))
        self.assertEqual(balance_sheet(date(2027, 1, 31))["totals"]["asset"], Decimal("0.00"))

    def test_pl_date_filter_and_bs_as_of_filter(self):
        self.entry(2, [(self.bank, "150.00", "0"), (self.sales, "0", "150.00")])
        self.entry(10, [(self.advertising, "30.00", "0"), (self.bank, "0", "30.00")])
        report = profit_and_loss(date(2027, 1, 5), date(2027, 1, 31))
        self.assertEqual(report["totals"]["income"], Decimal("0.00"))
        self.assertEqual(report["totals"]["expense"], Decimal("30.00"))
        self.assertEqual(balance_sheet(date(2027, 1, 5))["totals"]["asset"], Decimal("150.00"))
        self.assertEqual(balance_sheet(date(2027, 1, 31))["totals"]["asset"], Decimal("120.00"))

    def test_report_pages_render(self):
        self.entry(1, [(self.supplies, "45.50", "0"), (self.visa, "0", "45.50")])
        response = self.client.get(reverse("accounting:profit_loss"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gross profit")
        self.assertContains(response, "5004")
        self.assertContains(response, "45.50")
        response = self.client.get(reverse("accounting:balance_sheet"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Balance Sheet balances")
        self.assertContains(response, "Accumulated earnings")

    def test_reject_invalid_pl_dates(self):
        url = reverse("accounting:profit_loss")
        response = self.client.get(url, {"start": "2027-03-01", "end": "2027-02-01"})
        self.assertContains(response, "end date must be on or after")
        self.assertIsNone(response.context["report"])
        response = self.client.get(url, {"start": "2026-12-01", "end": "2027-01-01"})
        self.assertContains(response, "ledger starts January 1, 2027")
        self.assertIsNone(response.context["report"])

    def test_reject_pre_start_balance_sheet(self):
        response = self.client.get(reverse("accounting:balance_sheet"), {"as_of": "2026-12-31"})
        self.assertContains(response, "ledger starts January 1, 2027")
        self.assertIsNone(response.context["report"])

    def test_reports_staff_only(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounting:profit_loss")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounting:balance_sheet")).status_code, 302)
