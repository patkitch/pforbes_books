from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from accounting.models import Account, JournalEntry
from accounting_imports.models import ImportBatch, ImportRow, StripePaymentImport, WooOrderImport, WooPayoutMatch, StripePayoutMatch
from .sales_payout_report import build_report

class SalesPayoutReportTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="report",is_staff=True))
        self.url=reverse("accounting:sales_payout_report")
        self.bank=Account.objects.create(number="1002",name="Checking",account_type="asset")
        self.batch=ImportBatch.objects.create(account_id=self.bank.pk,filename="bank.csv")
        self.woo=WooOrderImport.objects.create(source_order_id=7366,order_date=date(2026,10,4),woo_status="completed",customer_name="Woo Buyer",total=Decimal("66.22"),tax_total=Decimal("6.22"),payment_method="Stripe",payload={"currency":"USD","payment_method":"stripe","date_paid":"2026-10-04T12:00:00"})
        self.payment=StripePaymentImport.objects.create(charge_id="ch_direct",payout_id="po_direct",created_utc=datetime(2026,10,18,12,tzinfo=timezone.utc),gross=Decimal("16.53"),fee=Decimal("0.78"),refunded=0,currency="usd",payment_status="paid",captured=True,review_data={"state":"reviewed","customer_name":"Direct Buyer","quantity":1,"unit_price":"16.53","shipping":"0","tax":"0"})
        StripePaymentImport.objects.create(charge_id="ch_woo",created_utc=datetime(2026,10,4,12,tzinfo=timezone.utc),gross=Decimal("66.22"),fee=Decimal("2.22"),refunded=0,currency="usd",payment_status="paid",captured=True,woo_order_number=7366)
        row=ImportRow.objects.create(batch=self.batch,account_id=self.bank.pk,transaction_date=date(2026,10,7),description="Stripe",amount=Decimal("64"),fingerprint="a"*64)
        WooPayoutMatch.objects.create(order=self.woo,bank_row=row,processor="Stripe",gross=Decimal("66.22"),fee=Decimal("2.22"),net=64,evidence="verified")
    def test_totals_no_duplicate(self):
        report=build_report()
        self.assertEqual(len(report["rows"]),2)
        self.assertEqual(report["totals"]["gross"],Decimal("82.75"))
        self.assertEqual(report["totals"]["fee"],Decimal("3.00"))
        self.assertEqual(report["totals"]["tax"],Decimal("6.22"))
        self.assertEqual(report["totals"]["deposit"],Decimal("64"))
        self.assertEqual(report["matched_count"],1)
        self.assertEqual(report["incomplete"]["deposit"],1)
        self.assertFalse(JournalEntry.objects.exists())
    def test_filters(self):
        self.assertEqual(len(build_report(source="stripe")["rows"]),1)
        self.assertEqual(len(build_report(end=date(2026,10,7))["rows"]),1)
        self.assertEqual(self.client.get(self.url,{"start":"2026-11-01","end":"2026-10-01","format":"pdf"}).status_code,400)
    def test_exports(self):
        response=self.client.get(self.url,{"format":"xlsx"})
        self.assertEqual(response.status_code,200)
        ws=load_workbook(BytesIO(response.content)).active
        self.assertEqual(ws["H6"].value,66.22)
        self.assertEqual(ws["H7"].value,16.53)
        self.assertTrue(self.client.get(self.url,{"format":"pdf"}).content.startswith(b"%PDF"))
        self.assertContains(self.client.get(self.url),"Woo Buyer")
    def test_nonstaff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.assertEqual(self.client.get(self.url,{"format":"xlsx"}).status_code,302)
