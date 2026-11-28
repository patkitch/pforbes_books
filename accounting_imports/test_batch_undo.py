from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportBatch, ImportRow
from .views import stage_rows


class BatchUndoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="undo_staff", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1002", name="Checking", account_type="asset")
        self.card = Account.objects.create(number="2004", name="Card", account_type="liability")
        self.rows = [{"date": date(2026, 11, 18), "description": "Amazon",
                      "amount": Decimal("-60.10"), "source_format": "boa_card", "reference": "123"}]
        self.correct, _, _ = stage_rows(self.card, "card.csv", self.rows, self.user)
        self.wrong, _, _ = stage_rows(self.bank, "card.csv", self.rows, self.user)
        self.url = reverse("accounting:undo_batch", args=[self.wrong.pk])

    def test_undo_only_wrong_batch_and_keep_history(self):
        ledger_count = JournalEntry.objects.count()
        self.assertContains(self.client.get(self.url), "Undo this import")
        self.assertEqual(ImportRow.objects.count(), 2)
        self.assertEqual(self.client.post(self.url, {"confirm": "yes"}).status_code, 302)
        self.wrong.refresh_from_db()
        self.assertEqual(self.wrong.undone_count, 1)
        self.assertEqual(self.wrong.undone_by, self.user)
        self.assertIsNotNone(self.wrong.undone_at)
        self.assertEqual(self.correct.rows.count(), 1)
        self.assertEqual(self.wrong.rows.count(), 0)
        self.assertEqual(JournalEntry.objects.count(), ledger_count)
        self.assertEqual(self.client.post(self.url, {"confirm": "yes"}).status_code, 400)
        self.assertContains(self.client.get(reverse("accounting:batch_history")), "Undone: 1 rows")

    def test_confirmation_required(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)
        self.assertEqual(self.wrong.rows.count(), 1)

    def test_reviewed_excluded_and_deferred_rows_block_undo(self):
        row = self.wrong.rows.get()
        for status, data in [(ImportRow.REVIEWED, {}), (ImportRow.EXCLUDED, {}),
                             (ImportRow.PENDING, {"classification": "deferred"})]:
            row.status, row.review_data = status, data
            row.save()
            self.assertEqual(self.client.post(self.url, {"confirm": "yes"}).status_code, 400)
            self.assertEqual(self.wrong.rows.count(), 1)

    def test_nonstaff_cannot_undo(self):
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(self.client.post(self.url, {"confirm": "yes"}).status_code, 302)
        self.assertEqual(self.wrong.rows.count(), 1)

    def test_empty_duplicate_batch_cannot_undo(self):
        duplicate, added, skipped = stage_rows(self.card, "card.csv", self.rows, self.user)
        self.assertEqual((added, skipped), (0, 1))
        url = reverse("accounting:undo_batch", args=[duplicate.pk])
        self.assertEqual(self.client.post(url, {"confirm": "yes"}).status_code, 400)
        self.assertEqual(self.correct.rows.count(), 1)
