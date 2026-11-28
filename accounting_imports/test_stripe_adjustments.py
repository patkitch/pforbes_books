from datetime import date,datetime,timezone
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import JournalEntry
from .models import StripeAdjustment,StripePaymentImport,WooOrderImport
from .stripe_payouts import candidates

class StripeAdjustmentTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="refund",is_staff=True))
        self.order=WooOrderImport.objects.create(source_order_id=88,order_date=date(2026,10,1),woo_status="completed",total=100,shipping_total=10,tax_total=5,payment_method="Stripe",payload={"currency":"USD","payment_method":"stripe","date_paid":"2026-10-01T12:00:00"})
        self.p=StripePaymentImport.objects.create(charge_id="ch_original",created_utc=datetime(2026,10,1,12,tzinfo=timezone.utc),gross=100,fee=3,refunded=0,currency="usd",payment_status="paid",captured=True,payout_id="po_original",woo_order_number=88)
        self.other=StripePaymentImport.objects.create(charge_id="ch_other",created_utc=datetime(2026,10,5,12,tzinfo=timezone.utc),gross=50,fee=2,refunded=0,currency="usd",payment_status="paid",captured=True,payout_id="po_later")
        self.url=reverse("accounting:stripe_adjustments")
    def add(self,**kw):
        return self.client.post(self.url,{"kind":"refund","balance_id":"txn_one","refund_id":"re_one","charge_id":"ch_original","payout_id":"po_later","day":"2026-10-05","artwork":"20","shipping":"0","tax":"0","amount":"-20","fee":"0","net":"-20","evidence":"Verified successful refund and payout detail","confirm":"on",**kw})
    def test_partial_preserves_original_and_duplicate(self):
        self.assertEqual(self.add().status_code,302)
        self.assertEqual(self.add().status_code,200)
        self.assertEqual(StripeAdjustment.objects.count(),1)
        self.p.refresh_from_db()
        self.assertEqual(self.p.gross,100)
        self.assertEqual(self.p.fee,3)
        self.assertFalse(JournalEntry.objects.exists())
    def test_full_refund(self):
        self.assertEqual(self.add(artwork="85",shipping="10",tax="5",amount="-100",net="-100").status_code,302)
        self.assertEqual(StripeAdjustment.objects.get().net,Decimal("-100"))
    def test_cumulative_and_component_limit(self):
        self.assertEqual(self.add().status_code,302)
        self.assertEqual(self.add(balance_id="txn_two",refund_id="re_two",artwork="66",amount="-66",net="-66").status_code,200)
        self.assertEqual(self.add(balance_id="txn_three",refund_id="re_three",artwork="0",tax="6",amount="-6",net="-6").status_code,200)
        self.assertEqual(StripeAdjustment.objects.count(),1)
    def test_net_and_confirmation(self):
        self.assertEqual(self.add(net="-19").status_code,200)
        self.assertEqual(self.add(confirm="").status_code,200)
        self.assertFalse(StripeAdjustment.objects.exists())
    def test_fee_credit_and_void(self):
        self.assertEqual(self.add(kind="fee",refund_id="",charge_id="",artwork="0",amount="0",fee="-2",net="2").status_code,302)
        a=StripeAdjustment.objects.get()
        self.assertEqual(self.client.post(self.url,{"action":"void","pk":a.pk,"reason":"Incorrect evidence","confirm":"yes"}).status_code,302)
        a.refresh_from_db()
        self.assertIsNotNone(a.voided_at)
        self.assertEqual(self.add().status_code,200)
    def test_unknown_payout(self):
        self.assertEqual(self.add(payout_id="po_unknown").status_code,200)
        self.assertFalse(StripeAdjustment.objects.exists())
