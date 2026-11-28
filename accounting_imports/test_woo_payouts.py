from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportBatch, ImportRow, WooOrderImport, WooPayoutMatch
from .woo_payouts import candidates


class WooPayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="payout", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1003", name="Advantage Savings (8596)", account_type="asset")
        self.batch = ImportBatch.objects.create(account_id=self.bank.pk, filename="bank.csv")
        self.order = self.make_order(7400)
        self.row = self.deposit()
        self.url = reverse("accounting:woo_payout", args=[self.order.pk])

    def make_order(self, number, **extra):
        fields = dict(source_order_id=number, order_date=date(2026,10,18), woo_status="completed",
            total=Decimal("800.01"), shipping_total=Decimal("200.01"), payment_method="Visa credit card",
            payload={"payment_method":"woocommerce_payments","currency":"USD","date_paid":"2026-10-18T12:00:00"})
        fields.update(extra)
        return WooOrderImport.objects.create(**fields)

    def deposit(self, **extra):
        fields = dict(batch=self.batch, account_id=self.bank.pk, transaction_date=date(2026,10,21),
            description="WooPayments DES:WooPayment", amount=Decimal("776.51"), fingerprint="a"*64)
        fields.update(extra)
        return ImportRow.objects.create(**fields)

    def confirm(self, url=None, **extra):
        data = {"action":"match", "bank_row":str(self.row.pk), "confirm":"yes", "evidence":"Verified processor payout."}
        data.update(extra)
        return self.client.post(url or self.url, data)

    def test_candidate_and_fee(self):
        rows = candidates(self.order)
        self.assertEqual([r.pk for r in rows], [self.row.pk])
        self.assertEqual(rows[0].calculated_fee, Decimal("23.50"))
        self.assertContains(self.client.get(self.url), "Advantage Savings")

    def test_match_no_posting(self):
        self.assertEqual(self.confirm().status_code,302)
        match = WooPayoutMatch.objects.get()
        self.assertEqual((match.gross,match.fee,match.net), (Decimal("800.01"),Decimal("23.50"),Decimal("776.51")))
        self.assertEqual(match.created_by,self.user)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status,ImportRow.PENDING)
        self.assertFalse(JournalEntry.objects.exists())

    def test_requires_confirmation_and_evidence(self):
        self.assertEqual(self.confirm(confirm="").status_code,400)
        self.assertEqual(self.confirm(evidence=" ").status_code,400)
        self.assertFalse(WooPayoutMatch.objects.exists())

    def test_duplicate_order_and_deposit(self):
        self.confirm()
        self.assertEqual(self.confirm().status_code,400)
        other = self.make_order(7401)
        self.assertEqual(self.confirm(reverse("accounting:woo_payout",args=[other.pk])).status_code,400)
        self.assertEqual(WooPayoutMatch.objects.count(),1)

    def test_database_constraint(self):
        self.confirm()
        other = self.make_order(7401)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WooPayoutMatch.objects.create(order=other,bank_row=self.row,processor="WooPayments",gross=self.order.total,
                fee=Decimal("23.50"),net=self.row.amount,evidence="duplicate")

    def test_wrong_processor_date_amount_and_status(self):
        for changes in ({"description":"STRIPE DES:TRANSFER"},{"transaction_date":date(2026,11,3)},
                        {"amount":Decimal("700")},{"amount":Decimal("801")},{"status":ImportRow.REVIEWED},
                        {"transaction_date":date(2026,10,17)}):
            original={k:getattr(self.row,k) for k in changes}
            ImportRow.objects.filter(pk=self.row.pk).update(**changes)
            self.assertEqual(candidates(self.order),[])
            ImportRow.objects.filter(pk=self.row.pk).update(**original)

    def test_ineligible_orders(self):
        for changes in ({"woo_status":"refunded"},{"woo_status":"cancelled"},{"review_status":"excluded"},
                        {"payload":{**self.order.payload,"refunds":[{"id":1}]}},
                        {"payload":{**self.order.payload,"currency":"EUR"}},
                        {"payload":{**self.order.payload,"date_paid":None}}):
            original={k:getattr(self.order,k) for k in changes}
            for k,v in changes.items(): setattr(self.order,k,v)
            self.assertEqual(candidates(self.order),[])
            for k,v in original.items(): setattr(self.order,k,v)

    def test_stripe_metadata_must_agree(self):
        self.order.payload={"payment_method":"stripe","currency":"USD","date_paid":"2026-10-18T12:00:00",
            "meta_data":[{"key":"_stripe_fee","value":"23.50"},{"key":"_stripe_net","value":"776.51"}]}
        self.order.payment_method="Google Pay (Stripe)"
        ImportRow.objects.filter(pk=self.row.pk).update(description="STRIPE DES:TRANSFER")
        self.assertEqual(len(candidates(self.order)),1)
        ImportRow.objects.filter(pk=self.row.pk).update(amount=Decimal("776.50"))
        self.assertEqual(candidates(self.order),[])

    def test_bank_and_order_protected(self):
        self.confirm()
        self.assertRedirects(self.client.get(reverse("accounting:bank_review",args=[self.row.pk])),self.url)
        self.assertEqual(self.client.post(reverse("accounting:import_status",args=[self.row.pk]),{"status":"excluded"}).status_code,400)
        self.assertEqual(self.client.post(reverse("accounting:woo_action",args=[self.order.pk]),{"action":"exclude"}).status_code,400)
        self.assertContains(self.client.get(reverse("accounting:import_inbox")),"View payout")
        self.assertContains(self.client.get(reverse("accounting:woo_inbox")),"Matched — not posted")

    def test_undo_and_rematch_preserves_history(self):
        self.confirm()
        self.assertEqual(self.client.post(self.url,{"action":"undo","confirm":"yes"}).status_code,302)
        old = WooPayoutMatch.objects.get()
        self.assertIsNotNone(old.undone_at)
        self.assertEqual(old.undone_by,self.user)
        self.assertEqual(len(candidates(self.order)),1)
        self.assertEqual(self.confirm().status_code,302)
        self.assertEqual(WooPayoutMatch.objects.count(),2)
        self.assertEqual(WooPayoutMatch.objects.filter(undone_at__isnull=True).count(),1)

    def test_nonstaff_cannot_match(self):
        self.client.force_login(get_user_model().objects.create_user(username="ordinary"))
        self.assertEqual(self.confirm().status_code,302)
        self.assertFalse(WooPayoutMatch.objects.exists())

    def test_unmatched_list_status(self):
        self.assertContains(self.client.get(reverse("accounting:woo_inbox")),"Unmatched")
