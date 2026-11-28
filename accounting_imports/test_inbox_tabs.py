from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from accounting_contacts.models import Vendor, Receipt
from .models import ImportRow
from .views import stage_rows


class InboxTabTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tab_staff", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1002", name="Checking", account_type="asset")
        self.card = Account.objects.create(number="2004", name="Credit card", account_type="liability")
        self.cost = Account.objects.create(number="5004", name="Materials", account_type="cogs")
        self.vendor = Vendor.objects.create(name="Test printer")
        batch, _, _ = stage_rows(self.card, "card.csv", [
            {"date": date(2026, 11, day), "description": name, "amount": Decimal("-20.00")}
            for day, name in [(17, "Reviewed purchase"), (18, "Personal purchase"), (19, "Pending purchase")]
        ], self.user)
        self.reviewed, self.excluded, self.pending = list(batch.rows.order_by("pk"))
        self.reviewed.status = ImportRow.REVIEWED
        self.reviewed.review_data = {"vendor": self.vendor.pk, "category": self.cost.pk, "memo": "Test memo"}
        self.reviewed.save()
        self.excluded.status = ImportRow.EXCLUDED
        self.excluded.save()
        batch, _, _ = stage_rows(self.bank, "bank.csv", [
            {"date": date(2026, 11, 20), "description": "Bank deposit", "amount": Decimal("35.00")}
        ], self.user)
        self.deposit = batch.rows.get()
        self.url = reverse("accounting:import_inbox")

    def test_default_review_and_counts(self):
        response = self.client.get(self.url)
        self.assertEqual({r.pk for r in response.context["items"]},
                         {self.reviewed.pk, self.pending.pk, self.deposit.pk})
        self.assertEqual([t["count"] for t in response.context["tabs"]], [3, 1, 0])
        self.assertContains(response, "Test printer")
        self.assertContains(response, "5004")
        self.assertContains(response, "−$20.00")

    def test_excluded_and_posted_are_separate(self):
        response = self.client.get(self.url, {"tab": "excluded"})
        self.assertEqual([r.pk for r in response.context["items"]], [self.excluded.pk])
        response = self.client.get(self.url, {"tab": "posted"})
        self.assertFalse(response.context["items"])
        self.assertContains(response, "No posted bank transactions")
        self.assertFalse(JournalEntry.objects.exists())

    def test_account_and_review_status_filters(self):
        response = self.client.get(self.url, {"account_filter": self.card.pk, "status_filter": "reviewed"})
        self.assertEqual([r.pk for r in response.context["items"]], [self.reviewed.pk])
        self.assertEqual([t["count"] for t in response.context["tabs"]], [2, 1, 0])

    def test_exclude_and_restore_moves_between_tabs(self):
        url = reverse("accounting:import_status", args=[self.pending.pk])
        self.client.post(url, {"status": "excluded", "tab": "review", "account_filter": self.card.pk})
        response = self.client.get(self.url, {"tab": "excluded", "account_filter": self.card.pk})
        self.assertEqual({r.pk for r in response.context["items"]}, {self.pending.pk, self.excluded.pk})
        response = self.client.post(url, {"status": "pending", "tab": "excluded", "account_filter": self.card.pk}, follow=True)
        self.assertIn(self.pending.pk, [r.pk for r in response.context["items"]])
        self.assertEqual(response.context["tab"], "review")
        self.assertFalse(JournalEntry.objects.exists())

    def test_document_indicator(self):
        Receipt.objects.create(title="Test invoice", receipt_type="purchase", date=self.reviewed.transaction_date,
            amount=Decimal("20.00"), vendor=self.vendor, source="bank_document",
            source_reference=f"{self.reviewed.pk}:test", attachment="test.pdf")
        response = self.client.get(self.url)
        item = next(r for r in response.context["items"] if r.pk == self.reviewed.pk)
        self.assertEqual(item.document_count, 1)
        self.assertContains(response, "1 document")
