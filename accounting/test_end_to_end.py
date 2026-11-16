"""Complete manual-accounting scenario to detect cross-module accounting errors."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry
from .reporting import balance_sheet, profit_and_loss


class FullManualWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="integrated_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.checking = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.savings = Account.objects.create(number="1002", name="Savings", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.contributions = Account.objects.create(number="3100", name="Owner contributions", account_type="equity")
        self.draws = Account.objects.create(number="3101", name="Owner draws", account_type="equity")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.supplies = Account.objects.create(number="5004", name="Art supplies", account_type="cogs")

    def submit(self, url_name, data):
        response = self.client.post(reverse(url_name), data)
        self.assertRedirects(response, reverse("accounting:transaction_list"))

    def test_full_month_postings_reconcile_without_duplicate_expenses(self):
        # $500 owner money to checking, NOT taxable sales.
        self.submit("accounting:owner_new", {
            "kind": "cash", "date": "2027-01-02", "payee": "Owner",
            "description": "Owner cash contribution", "amount": "500",
            "contribution_account": str(self.contributions.pk),
            "destination_account": str(self.checking.pk),
            "save_action": "post",
        })
        # $300 sale deposited in checking.
        self.submit("accounting:transaction_new", {
            "kind": "income", "date": "2027-01-03", "payee": "Customer",
            "description": "Artwork sold", "amount": "300",
            "category_account": str(self.sales.pk),
            "payment_account": str(self.checking.pk),
            "save_action": "post",
        })
        # $100 art supplies charged to the business Visa.
        self.submit("accounting:transaction_new", {
            "kind": "expense", "date": "2027-01-04", "payee": "Supply store",
            "description": "Paint and canvas", "amount": "100",
            "category_account": str(self.supplies.pk),
            "payment_account": str(self.card.pk),
            "save_action": "post",
        })
        def movement(kind, amount, debit, credit, day):
            self.submit("accounting:movement_new", {
                "kind": kind, "date": f"2027-01-{day:02d}",
                "description": kind.replace("_", " "),
                "amount": str(amount), "debit_account": str(debit.pk),
                "credit_account": str(credit.pk), "save_action": "post",
            })
        # $60 Visa payment is a liability settlement, NOT a second supply expense.
        movement("card_payment", 60, self.card, self.checking, 5)
        # $200 checking to savings is NOT an operating expense.
        movement("transfer", 200, self.savings, self.checking, 6)
        # $20 purchase refund to Visa reduces original COGS and card balance.
        movement("purchase_refund", 20, self.card, self.supplies, 7)
        # $50 draw is an equity withdrawal, NOT an operating expense.
        movement("owner_draw", 50, self.draws, self.checking, 8)

        pl = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        bs = balance_sheet(date(2027, 1, 31))
        self.assertEqual(pl["totals"]["income"], Decimal("300"))
        self.assertEqual(pl["totals"]["cogs"], Decimal("80"))
        self.assertEqual(pl["net_profit"], Decimal("220"))
        self.assertEqual(bs["totals"]["asset"], Decimal("690"))
        self.assertEqual(bs["totals"]["liability"], Decimal("20"))
        self.assertEqual(bs["totals"]["equity"], Decimal("450"))
        self.assertEqual(bs["earnings"], Decimal("220"))
        self.assertEqual(bs["liabilities_and_equity"], Decimal("690"))
        self.assertEqual(bs["difference"], Decimal("0"))
        self.assertTrue(bs["balanced"])

        # An erroneous extra $40 sale and audited reversing entry net to zero.
        self.submit("accounting:transaction_new", {
            "kind": "income", "date": "2027-01-10", "payee": "Test",
            "description": "Wrong sale", "amount": "40",
            "category_account": str(self.sales.pk),
            "payment_account": str(self.checking.pk),
            "save_action": "post",
        })
        wrong = JournalEntry.objects.get(description="Wrong sale")
        response = self.client.post(
            reverse("accounting:transaction_reverse", args=[wrong.pk]),
            {"date": "2027-01-11", "reason": "Duplicate entry"},
        )
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        pl_after = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        bs_after = balance_sheet(date(2027, 1, 31))
        self.assertEqual(pl_after["net_profit"], Decimal("220"))
        self.assertEqual(bs_after["totals"]["asset"], Decimal("690"))
        self.assertTrue(bs_after["balanced"])
