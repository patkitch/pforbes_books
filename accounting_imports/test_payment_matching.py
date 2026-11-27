from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportRow, CardPaymentMatch
from .payment_matching import candidates
from .views import stage_rows


class PaymentMatchingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="match_staff", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1003", name="Savings (1111)", account_type="asset")
        self.card = Account.objects.create(number="2004", name="Visa (2222)", account_type="liability")
        self.other = Account.objects.create(number="2003", name="Visa (3333)", account_type="liability")
        self.equity = Account.objects.create(number="3004", name="Owner investments", account_type="equity")
        self.day = date(2026, 10, 23)
        self.outgoing = self.stage(self.bank, "-889.58", "Mobile Banking payment to CRD 2222 Confirmation# abc123")
        self.outgoing.status = ImportRow.REVIEWED
        self.outgoing.review_data = {"classification": "card_payment", "payment_card": self.card.pk,
            "payment_funding": "personal", "payment_equity": self.equity.pk, "payment_business": "150.00"}
        self.outgoing.save(update_fields=["status", "review_data"])
        self.incoming = self.stage(self.card, "889.58", "PAYMENT FROM SAV 1111 CONF#ABC123")
        self.url = reverse("accounting:payment_match", args=[self.outgoing.pk])

    def stage(self, account, amount, description, days=0):
        batch, _, _ = stage_rows(account, "test.csv", [{"date": self.day + timedelta(days=days),
            "description": description, "amount": Decimal(amount)}], self.user)
        return batch.rows.get()

    def match(self, **overrides):
        data = {"action": "match", "card_row": self.incoming.pk, "confirm": "yes"}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_exact_match_and_confirmation_case(self):
        self.assertEqual(list(candidates(self.outgoing)), [self.incoming])
        self.assertEqual(self.match().status_code, 302)
        match = CardPaymentMatch.objects.get()
        self.assertEqual(match.bank_row_id, self.outgoing.pk)
        self.assertEqual(match.card_row_id, self.incoming.pk)
        self.assertEqual(match.created_by, self.user)
        self.assertFalse(JournalEntry.objects.exists())
        self.incoming.refresh_from_db()
        self.assertEqual(self.incoming.amount, Decimal("889.58"))
        self.assertEqual(self.incoming.status, ImportRow.PENDING)

    def test_wrong_confirmation_excluded(self):
        self.incoming.description = "PAYMENT CONF#DIFFERENT"
        self.incoming.save(update_fields=["description"])
        self.assertFalse(candidates(self.outgoing).exists())
        self.assertEqual(self.match().status_code, 400)

    def test_wrong_amount_and_card_excluded(self):
        self.stage(self.card, "150.00", "PAYMENT CONF#ABC123")
        self.stage(self.other, "889.58", "PAYMENT CONF#ABC123")
        self.assertEqual(list(candidates(self.outgoing)), [self.incoming])

    def test_date_window(self):
        inside = self.stage(self.card, "889.58", "PAYMENT", days=7)
        self.stage(self.card, "889.58", "PAYMENT", days=8)
        self.assertEqual(set(candidates(self.outgoing)), {self.incoming, inside})

    def test_refund_not_payment(self):
        self.stage(self.card, "889.58", "MERCHANT REFUND CONF#ABC123")
        self.assertEqual(list(candidates(self.outgoing)), [self.incoming])

    def test_explicit_confirmation_required(self):
        self.assertEqual(self.match(confirm="").status_code, 400)
        self.assertFalse(CardPaymentMatch.objects.exists())

    def test_duplicate_match_rejected(self):
        self.assertEqual(self.match().status_code, 302)
        self.assertEqual(self.match().status_code, 400)
        self.assertEqual(CardPaymentMatch.objects.count(), 1)

    def test_database_unique_active_card_match(self):
        self.match()
        another = self.stage(self.bank, "-889.58", "Another payment")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CardPaymentMatch.objects.create(bank_row=another, card_row=self.incoming, created_by=self.user)

    def test_matched_records_cannot_be_edited_or_excluded(self):
        self.match()
        for row in (self.outgoing, self.incoming):
            self.assertRedirects(self.client.post(reverse("accounting:bank_review", args=[row.pk]),
                {"classification": "personal"}), reverse("accounting:payment_match", args=[row.pk]))
            self.assertEqual(self.client.post(reverse("accounting:import_status", args=[row.pk]),
                {"status": "excluded"}).status_code, 400)

    def test_undo_from_card_side_and_rematch(self):
        self.match()
        url = reverse("accounting:payment_match", args=[self.incoming.pk])
        self.assertEqual(self.client.post(url, {"action": "undo", "confirm": "yes"}).status_code, 302)
        old = CardPaymentMatch.objects.get()
        self.assertIsNotNone(old.undone_at)
        self.assertEqual(old.undone_by, self.user)
        self.assertEqual(list(candidates(self.outgoing)), [self.incoming])
        self.assertEqual(self.match().status_code, 302)
        self.assertEqual(CardPaymentMatch.objects.count(), 2)
        self.assertEqual(CardPaymentMatch.objects.filter(undone_at__isnull=True).count(), 1)
        self.assertFalse(JournalEntry.objects.exists())

    def test_undo_requires_confirmation(self):
        self.match()
        self.assertEqual(self.client.post(self.url, {"action": "undo"}).status_code, 400)
        self.assertIsNone(CardPaymentMatch.objects.get().undone_at)

    def test_inbox_single_match_status(self):
        self.match()
        response = self.client.get(reverse("accounting:import_inbox"))
        self.assertContains(response, "Matched — not posted", count=2)
        self.assertContains(response, "View match", count=2)

    def test_undo_import_preserves_match_history(self):
        self.match()
        self.client.post(self.url, {"action": "undo", "confirm": "yes"})
        response = self.client.post(reverse("accounting:undo_batch", args=[self.incoming.batch_id]), {"confirm": "yes"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ImportRow.objects.filter(pk=self.incoming.pk).exists())

    def test_nonstaff_cannot_match(self):
        self.client.logout()
        self.assertEqual(self.match().status_code, 302)
        self.assertFalse(CardPaymentMatch.objects.exists())
