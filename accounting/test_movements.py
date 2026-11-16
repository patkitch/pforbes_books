from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry
from .reporting import balance_sheet, profit_and_loss


class ManualCoreMovementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="movement_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.checking = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.savings = Account.objects.create(number="1002", name="Savings", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.equity = Account.objects.create(number="3100", name="Owner draws", account_type="equity")
        self.income = Account.objects.create(number="4001", name="Art sales", account_type="income")
        self.cogs = Account.objects.create(number="5004", name="Supplies", account_type="cogs")

    def payload(self, kind, debit, credit, action="post", **overrides):
        data = {
            "kind": kind, "date": "2027-01-15", "payee": "Test",
            "description": "Core movement test", "amount": "100.00",
            "debit_account": str(debit.pk), "credit_account": str(credit.pk),
            "memo": "", "save_action": action,
        }
        data.update(overrides)
        return data

    def make(self, kind, debit, credit, **extra):
        response = self.client.post(
            reverse("accounting:movement_new"), self.payload(kind, debit, credit, **extra)
        )
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        return JournalEntry.objects.order_by("-pk").first()

    def statements(self):
        pl = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        bs = balance_sheet(date(2027, 1, 31))
        self.assertTrue(bs["balanced"])
        return pl, bs

    def test_bank_transfer_does_not_change_profit_or_total_assets(self):
        entry = self.make("transfer", self.savings, self.checking)
        self.assertEqual(entry.lines.get(account=self.savings).debit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.checking).credit, Decimal("100.00"))
        pl, bs = self.statements()
        self.assertEqual(pl["net_profit"], Decimal("0.00"))
        self.assertEqual(bs["totals"]["asset"], Decimal("0.00"))

    def test_credit_card_payment_reduces_liability_without_expense(self):
        entry = self.make("card_payment", self.card, self.checking)
        self.assertEqual(entry.lines.get(account=self.card).debit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.checking).credit, Decimal("100.00"))
        pl, bs = self.statements()
        self.assertEqual(pl["net_profit"], Decimal("0.00"))
        self.assertEqual(bs["totals"]["liability"], Decimal("-100.00"))

    def test_owner_draw_reduces_equity_not_profit(self):
        self.make("owner_draw", self.equity, self.checking)
        pl, bs = self.statements()
        self.assertEqual(pl["net_profit"], Decimal("0.00"))
        self.assertEqual(bs["totals"]["equity"], Decimal("-100.00"))

    def test_personal_funds_pay_card_as_owner_equity_not_expense(self):
        entry = self.make("owner_card_payment", self.card, self.equity)
        self.assertEqual(entry.lines.get(account=self.card).debit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.equity).credit, Decimal("100.00"))
        pl, bs = self.statements()
        self.assertEqual(pl["net_profit"], Decimal("0.00"))
        self.assertEqual(bs["totals"]["liability"], Decimal("-100.00"))
        self.assertEqual(bs["totals"]["equity"], Decimal("100.00"))

    def test_purchase_refund_reverses_expense_and_reduces_card_debt(self):
        self.make("purchase_refund", self.card, self.cogs)
        pl, bs = self.statements()
        self.assertEqual(pl["totals"]["cogs"], Decimal("-100.00"))
        self.assertEqual(bs["totals"]["liability"], Decimal("-100.00"))

    def test_sales_refund_reverses_revenue(self):
        self.make("sales_refund", self.income, self.checking)
        pl, bs = self.statements()
        self.assertEqual(pl["totals"]["income"], Decimal("-100.00"))
        self.assertEqual(bs["totals"]["asset"], Decimal("-100.00"))

    def test_draft_edit_post_does_not_duplicate(self):
        entry = self.make("transfer", self.savings, self.checking, action="draft")
        self.assertEqual(entry.status, "draft")
        url = reverse("accounting:movement_edit", args=[entry.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            url, self.payload("transfer", self.savings, self.checking, amount="75.75")
        )
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(entry.lines.get(account=self.savings).debit, Decimal("75.75"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_invalid_account_combinations_do_not_post(self):
        url = reverse("accounting:movement_new")
        combinations = [
            ("transfer", self.card, self.checking),
            ("card_payment", self.savings, self.checking),
            ("owner_draw", self.equity, self.card),
            ("purchase_refund", self.checking, self.income),
            ("sales_refund", self.cogs, self.checking),
            ("transfer", self.checking, self.checking),
        ]
        for kind, debit, credit in combinations:
            with self.subTest(kind=kind):
                resp = self.client.post(url, self.payload(kind, debit, credit))
                self.assertEqual(resp.status_code, 200)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_dates_earlier_than_2027_rejected(self):
        resp = self.client.post(
            reverse("accounting:movement_new"),
            self.payload("transfer", self.savings, self.checking, date="2026-12-31"),
        )
        self.assertContains(resp, "begins January 1, 2027")
        self.assertFalse(JournalEntry.objects.exists())

    def test_nonstaff_cannot_create_movement(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        resp = self.client.post(
            reverse("accounting:movement_new"),
            self.payload("transfer", self.savings, self.checking),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(JournalEntry.objects.exists())

    def test_register_has_movement_and_reversal_links(self):
        entry = self.make("transfer", self.savings, self.checking)
        resp = self.client.get(reverse("accounting:transaction_list"))
        self.assertContains(resp, "Transfer / card payment / refund")
        self.assertContains(resp, reverse("accounting:transaction_reverse", args=[entry.pk]))
