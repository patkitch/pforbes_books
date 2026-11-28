from datetime import date, datetime, timezone
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from accounting_contacts.models import Receipt
from accounting.sales_payout_report import build_report
from .models import ImportBatch, ImportRow, StripePaymentImport, WooOrderImport, StripeGroupMatch, WooPayoutMatch

class StripeGroupTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="group",is_staff=True))
        self.bank=Account.objects.create(number="1003",name="Advantage Savings (8596)",account_type="asset")
        batch=ImportBatch.objects.create(account_id=self.bank.pk,filename="bank.csv")
        self.row=ImportRow.objects.create(batch=batch,account_id=self.bank.pk,transaction_date=date(2026,10,7),description="STRIPE DES:TRANSFER",amount=Decimal("145.05"),fingerprint="c"*64)
        self.order=WooOrderImport.objects.create(source_order_id=777,order_date=date(2026,10,4),woo_status="completed",customer_name="Woo",total=100,payment_method="Stripe",payload={"currency":"USD","payment_method":"stripe","date_paid":"2026-10-04T12:00:00"})
        common=dict(payout_id="po_group",created_utc=datetime(2026,10,4,12,tzinfo=timezone.utc),refunded=0,currency="usd",payment_status="paid",captured=True)
        self.woo=StripePaymentImport.objects.create(charge_id="ch_woo",gross=100,fee=Decimal("3.20"),woo_order_number=777,**common)
        receipt=Receipt.objects.create(source="stripe_direct",source_reference="ch_direct",title="Direct",receipt_type="sale",date=date(2026,10,4),amount=50)
        self.direct=StripePaymentImport.objects.create(charge_id="ch_direct",gross=50,fee=Decimal("1.75"),review_data={"state":"reviewed","receipt_id":receipt.pk,"quantity":1,"unit_price":"50","shipping":"0","tax":"0"},**common)
        self.url=reverse("accounting:stripe_group",args=["po_group"])
    def confirm(self,**kw):
        return self.client.post(self.url,{"action":"match","confirm":"yes","bank_row":self.row.pk,"evidence":"Verified complete payout",**kw})
    def test_match_report_undo(self):
        self.assertContains(self.client.get(self.url),"145.05")
        self.assertEqual(self.confirm().status_code,302)
        g=StripeGroupMatch.objects.get()
        self.assertEqual(g.members.count(),2)
        self.assertEqual(build_report()["totals"]["deposit"],Decimal("145.05"))
        self.assertEqual(build_report(source="stripe")["totals"]["deposit"],Decimal("48.25"))
        self.assertEqual(build_report()["matched_count"],2)
        self.assertEqual(self.confirm().status_code,400)
        self.assertEqual(self.client.post(self.url,{"action":"undo","confirm":"yes"}).status_code,302)
        self.assertEqual(build_report()["matched_count"],0)
        self.assertEqual(self.confirm().status_code,302)
        self.assertEqual(StripeGroupMatch.objects.count(),2)
        self.assertFalse(JournalEntry.objects.exists())
    def test_wrong_amount_and_refund(self):
        self.row.amount=Decimal("145.04")
        self.row.save(update_fields=["amount"])
        self.assertEqual(self.confirm().status_code,400)
        self.row.amount=Decimal("145.05")
        self.row.save(update_fields=["amount"])
        self.direct.refunded=1
        self.direct.save(update_fields=["refunded"])
        self.assertEqual(self.confirm().status_code,400)
    def test_bank_protection(self):
        self.assertEqual(self.confirm().status_code,302)
        self.assertEqual(self.client.post(reverse("accounting:import_status",args=[self.row.pk]),{"status":"excluded"}).status_code,400)
        self.assertRedirects(self.client.get(reverse("accounting:bank_review",args=[self.row.pk])),self.url)
        self.assertEqual(self.client.post(reverse("accounting:woo_action",args=[self.order.pk]),{"action":"exclude"}).status_code,400)
    def test_existing_individual_match_blocks_group(self):
        WooPayoutMatch.objects.create(order=self.order,bank_row=self.row,processor="Stripe",gross=100,fee=Decimal("3.20"),net=Decimal("96.80"),evidence="existing")
        self.assertEqual(self.confirm().status_code,400)
    def test_requires_confirmation(self):
        self.assertEqual(self.confirm(confirm="").status_code,400)
        self.assertEqual(self.confirm(evidence="").status_code,400)
