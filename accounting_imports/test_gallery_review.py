from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportRow
from .views import stage_rows


class GalleryReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gallery_staff", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1003", name="Savings", account_type="asset")
        self.card = Account.objects.create(number="2004", name="Visa (4621)", account_type="liability")
        self.income = Account.objects.create(number="4013", name="Gallery Commission", account_type="income")
        self.other_income = Account.objects.create(number="4011", name="Original Art Sales", account_type="income")
        self.commission = Account.objects.create(number="6008", name="Commissions & fees", account_type="expense")
        batch, _, _ = stage_rows(self.bank, "test.csv", [
            {"date": date(2026, 10, 23), "description": "Mobile check deposit", "amount": Decimal("77.00")}
        ], self.user)
        self.row = batch.rows.get()
        self.url = reverse("accounting:bank_review", args=[self.row.pk])

    def values(self, **overrides):
        data = {"classification": "gallery", "gallery_name": "Images Art Gallery",
                "gallery_period": "2026-09", "gallery_received": "2026-10-20",
                "gallery_gross": "110.00", "gallery_rate": "30",
                "gallery_income": self.income.pk, "gallery_commission_account": self.commission.pk}
        data.update(overrides)
        return data

    def reject(self, **overrides):
        response = self.client.post(self.url, self.values(**overrides))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(JournalEntry.objects.exists())

    def test_defaults(self):
        initial = self.client.get(self.url).context["form"].initial
        self.assertEqual(initial["gallery_name"], "Images Art Gallery")
        self.assertEqual(initial["gallery_rate"], Decimal("30"))
        self.assertEqual(initial["gallery_income"], self.income.pk)
        self.assertEqual(initial["gallery_commission_account"], self.commission.pk)
        self.assertEqual(initial["gallery_period"], "2026-09")

    def test_balanced_gallery_review_and_reload(self):
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.REVIEWED)
        self.assertEqual(self.row.amount, Decimal("77.00"))
        self.assertEqual(self.row.review_data["gallery_gross"], "110.00")
        self.assertEqual(self.row.review_data["gallery_commission"], "33.00")
        self.assertEqual(self.row.review_data["gallery_period"], "2026-09-01")
        self.assertEqual(self.row.review_data["gallery_received"], "2026-10-20")
        self.assertEqual(self.row.review_data["gallery_income"], self.income.pk)
        self.assertEqual(self.client.get(self.url).context["form"].initial["gallery_period"], "2026-09")
        self.assertFalse(JournalEntry.objects.exists())

    def test_editable_defaults(self):
        self.assertEqual(self.client.post(self.url, self.values(gallery_name="Another gallery",
            gallery_gross="100", gallery_rate="23", gallery_income=self.other_income.pk)).status_code, 302)
        initial = self.client.get(self.url).context["form"].initial
        self.assertEqual(initial["gallery_name"], "Another gallery")
        self.assertEqual(initial["gallery_rate"], "23.00")
        self.assertEqual(initial["gallery_income"], self.other_income.pk)

    def test_invalid_edit_preserves_review(self):
        self.client.post(self.url, self.values())
        self.row.refresh_from_db()
        previous = self.row.review_data.copy()
        self.reject(gallery_gross="120")
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data, previous)

    def test_invalid_commission_rates(self):
        for rate in ("-1", "101", "30.001", ""):
            with self.subTest(rate=rate):
                self.reject(gallery_rate=rate)

    def test_invalid_gross(self):
        for gross in ("0", "-110", "110.001", ""):
            with self.subTest(gross=gross):
                self.reject(gallery_gross=gross)

    def test_wrong_account_types(self):
        self.reject(gallery_income=self.commission.pk)
        self.reject(gallery_commission_account=self.income.pk)

    def test_invalid_dates(self):
        self.reject(gallery_received="2026-10-24")
        self.reject(gallery_period="2026-11")
        self.reject(gallery_period="2026-09-02")
        self.reject(gallery_period="2026-13")

    def test_zero_commission(self):
        self.assertEqual(self.client.post(self.url, self.values(gallery_gross="77", gallery_rate="0")).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data["gallery_commission"], "0.00")

    def test_round_half_up(self):
        self.row.amount = Decimal("0.01")
        self.row.save(update_fields=["amount"])
        self.assertEqual(self.client.post(self.url, self.values(gallery_gross="0.02", gallery_rate="25")).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data["gallery_commission"], "0.01")

    def test_card_credit_not_gallery_deposit(self):
        self.row.account_id = self.card.pk
        self.row.save(update_fields=["account_id"])
        self.reject()

    def test_deferred_clears_gallery_fields(self):
        self.client.post(self.url, self.values())
        self.assertEqual(self.client.post(self.url, {"classification": "deferred"}).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
        self.assertIsNone(self.row.review_data["gallery_gross"])

    def test_nonstaff_cannot_save(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
