from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from .models import ImportBatch, ImportRow, StripePaymentImport, StripePayoutMatch, WooOrderImport, WooPayoutMatch
from .stripe_payouts import candidates

class StripePayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="stripe-payout", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1003", name="Advantage Savings (8596)", account_type="asset")
        batch = ImportBatch.objects.create(account_id=self.bank.pk, filename="bank.csv")
        self.row = ImportRow.objects.create(batch=batch, account_id=self.bank.pk, transaction_date=date(2026,10,21),
            description="STRIPE DES:TRANSFER", amount=Decimal("15.75"), fingerprint="b"*64)
        self.payment = StripePaymentImport.objects.create(charge_id="ch_test", payout_id="po_test", created_utc=datetime(2026,10,18,12,tzinfo=timezone.utc),
            gross=Decimal("16.53"), fee=Decimal("0.78"), refunded=0, currency="usd", payment_status="paid", captured=True,
            review_data={"state":"reviewed","receipt_id":1})
        self.url = reverse("accounting:stripe_payout", args=[self.payment.pk])
        self.receipt = patch("accounting_imports.stripe_payouts.Receipt.objects.filter")
        mock = self.receipt.start()
        mock.return_value.exists.return_value = True
        self.addCleanup(self.receipt.stop)

    def confirm(self, **extra):
        data = {"action":"match","bank_row":str(self.row.pk),"confirm":"yes","evidence":"Verified single charge payout"}
        data.update(extra)
        return self.client.post(self.url,data)

    def test_match_undo_rematch(self):
        # Candidate document lookup uses the same Receipt manager; isolate that check.
        with patch("accounting_imports.stripe_payouts.has_documents", return_value=False):
            self.assertEqual(self.confirm().status_code,302)
            self.assertEqual(self.confirm().status_code,400)
            match = StripePayoutMatch.objects.get()
            self.assertEqual(match.net,Decimal("15.75"))
            self.assertEqual(match.created_by,self.user)
            self.assertEqual(self.client.post(self.url,{"action":"undo","confirm":"yes"}).status_code,302)
            match.refresh_from_db()
            self.assertEqual(match.undone_by,self.user)
            self.assertEqual(self.confirm().status_code,302)
            self.assertEqual(StripePayoutMatch.objects.count(),2)
            self.assertFalse(JournalEntry.objects.exists())

    def test_wrong_amount_and_no_confirmation(self):
        with patch("accounting_imports.stripe_payouts.has_documents", return_value=False):
            self.assertEqual(self.confirm(confirm="").status_code,400)
            self.row.amount=Decimal("15.74")
            self.row.save(update_fields=["amount"])
            self.assertEqual(candidates(self.payment),[])
            self.assertEqual(self.confirm().status_code,400)

    def test_woo_deposit_already_used(self):
        order=WooOrderImport.objects.create(source_order_id=123,order_date=date(2026,10,18),woo_status="completed",total=Decimal("16.53"),payload={})
        WooPayoutMatch.objects.create(order=order,bank_row=self.row,processor="Stripe",gross=Decimal("16.53"),fee=Decimal("0.78"),net=self.row.amount,evidence="existing")
        with patch("accounting_imports.stripe_payouts.has_documents", return_value=False):
            self.assertEqual(self.confirm().status_code,400)

    def test_grouped_payout_blocked(self):
        StripePaymentImport.objects.create(charge_id="ch_other",payout_id=self.payment.payout_id,created_utc=self.payment.created_utc,
            gross=10,fee=1,refunded=0,currency="usd",payment_status="paid",captured=True)
        self.assertEqual(candidates(self.payment),[])
