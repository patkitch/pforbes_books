from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportRow
from .views import stage_rows


class CardPaymentReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="payment_staff", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1003", name="Savings", account_type="asset")
        self.card = Account.objects.create(number="2004", name="Visa (4621)", account_type="liability")
        self.other = Account.objects.create(number="2003", name="Visa (6245)", account_type="liability")
        self.equity = Account.objects.create(number="3004", name="Owner investments", account_type="equity")
        self.draw = Account.objects.create(number="3005", name="Owner draws", account_type="equity")
        self.expense = Account.objects.create(number="5004", name="Materials", account_type="cogs")
        batch, _, _ = stage_rows(self.bank, "test.csv", [
            {"date": date(2026, 10, 23), "description": "Mobile Banking payment to CRD 4621", "amount": Decimal("-889.58")}
        ], self.user)
        self.row = batch.rows.get()
        self.url = reverse("accounting:bank_review", args=[self.row.pk])

    def values(self, **overrides):
        data = {"classification": "card_payment", "payment_card": self.card.pk,
                "payment_funding": "personal", "payment_equity": self.equity.pk,
                "payment_business": "150.00", "memo": "Test payment"}
        data.update(overrides)
        return data

    def reject(self, **overrides):
        response = self.client.post(self.url, self.values(**overrides))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(JournalEntry.objects.exists())

    def test_personal_funding_partial_payment_and_reload(self):
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.REVIEWED)
        self.assertEqual(self.row.amount, Decimal("-889.58"))
        self.assertEqual(self.row.review_data["payment_business"], "150.00")
        self.assertEqual(self.row.review_data["payment_remainder"], "739.58")
        self.assertEqual(self.row.review_data["payment_equity"], self.equity.pk)
        self.assertEqual(self.client.get(self.url).context["form"].initial["payment_card"], self.card.pk)
        self.assertFalse(JournalEntry.objects.exists())

    def test_business_funding_without_equity(self):
        self.assertEqual(self.client.post(self.url, self.values(payment_funding="business", payment_equity="")).status_code, 302)
        self.row.refresh_from_db()
        self.assertIsNone(self.row.review_data["payment_equity"])
        self.assertEqual(self.row.review_data["payment_funding"], "business")
        self.assertFalse(JournalEntry.objects.exists())

    def test_invalid_amounts(self):
        for amount in ("900", "0", "-1", "1.001", ""):
            with self.subTest(amount=amount):
                self.reject(payment_business=amount)

    def test_wrong_card_suffix_rejected(self):
        self.reject(payment_card=self.other.pk)

    def test_invalid_account_choices(self):
        self.reject(payment_card=self.bank.pk)
        self.reject(payment_equity=self.draw.pk)

    def test_funding_requirements(self):
        self.reject(payment_funding="")
        self.reject(payment_equity="")
        self.reject(payment_funding="business")

    def test_expense_category_rejected(self):
        self.reject(category=self.expense.pk)

    def test_invalid_edit_preserves_saved_review(self):
        self.client.post(self.url, self.values())
        self.row.refresh_from_db()
        previous = self.row.review_data.copy()
        self.reject(payment_business="900")
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data, previous)

    def test_deferred_clears_payment_allocation(self):
        self.client.post(self.url, self.values())
        self.assertEqual(self.client.post(self.url, {"classification": "deferred"}).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
        self.assertIsNone(self.row.review_data["payment_business"])
        self.assertIsNone(self.row.review_data["payment_card"])

    def test_positive_card_side_credit_rejected(self):
        self.row.account_id = self.card.pk
        self.row.amount = Decimal("889.58")
        self.row.save(update_fields=["account_id", "amount"])
        self.reject()

    def test_full_payment_formats_zero_remainder(self):
        self.assertEqual(self.client.post(self.url, self.values(payment_business="889.58")).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data["payment_remainder"], "0.00")

    def test_nonstaff_cannot_save_payment(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
