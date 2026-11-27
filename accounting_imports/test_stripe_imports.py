import csv
import io
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account, JournalEntry
from accounting_contacts.models import Customer, Receipt
from .models import StripePaymentImport, WooOrderImport
from .stripe_imports import stage, classify


def export(*changes):
    base = {"id":"ch_test1","Created date (UTC)":"2026-10-18 18:00:00","Amount":"16.53",
        "Amount Refunded":"0.00","Currency":"usd","Captured":"true","Fee":"0.78","Status":"Paid",
        "Transfer":"po_test1","order_id (metadata)":"","Converted Currency":"usd","Converted Amount":"16.53",
        "Converted Amount Refunded":"0.00","Taxes On Fee":"0.00","Customer Email":"buyer@example.com"}
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fieldnames=list(base))
    writer.writeheader()
    for update in changes or ({},):
        writer.writerow({**base,**update})
    return stream.getvalue().encode()


class StripeImportTests(TestCase):
    def setUp(self):
        self.actor=get_user_model().objects.create_user(username="stripe",is_staff=True)
        self.client.force_login(self.actor)
        self.revenue=Account.objects.create(number="4012",name="Print Sales",account_type="income")

    def payment(self, **changes):
        stage(export(changes),self.actor)
        return StripePaymentImport.objects.get()

    def woo(self, **changes):
        fields=dict(source_order_id=123,order_date="2026-10-18",woo_status="completed",
            total=Decimal("16.53"),payment_method="Stripe",payload={"payment_method":"stripe"})
        return WooOrderImport.objects.create(**{**fields,**changes})

    def form(self, **changes):
        return {"action":"save","customer_name":"Test Buyer","customer_email":"buyer@example.com",
            "artwork":"Print","item_type":"print","quantity":"1","unit_price":"16.53","shipping":"0",
            "tax":"0","revenue":str(self.revenue.pk),"confirm":"on",**changes}

    def test_import_duplicate_no_sale(self):
        self.assertEqual(stage(export(),self.actor),(1,0))
        self.assertEqual(stage(export(),self.actor),(0,1))
        self.assertEqual(StripePaymentImport.objects.count(),1)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertFalse(Receipt.objects.exists())

    def test_changed_export_atomic(self):
        self.payment()
        with self.assertRaises(ValidationError):
            stage(export({"id":"ch_new"},{"Fee":"0.79"}),self.actor)
        self.assertEqual(StripePaymentImport.objects.count(),1)

    def test_invalid_money(self):
        with self.assertRaises(ValidationError):
            stage(export({"Amount":"NaN"}),self.actor)
        self.assertFalse(StripePaymentImport.objects.exists())

    def test_duplicate_within_file(self):
        with self.assertRaises(ValidationError):
            stage(export({},{}),self.actor)

    def test_woo_wait_then_link(self):
        p=self.payment(**{"order_id (metadata)":"123"})
        self.assertIn("Waiting",classify(p)[0])
        order=self.woo()
        self.assertEqual(classify(p),("WooCommerce linked — no new sale",order))

    def test_woo_conflict(self):
        p=self.payment(**{"order_id (metadata)":"123"})
        self.woo(total=Decimal("17.00"))
        self.assertIn("conflict",classify(p)[0])

    def test_charge_reference_prevents_direct(self):
        p=self.payment()
        self.woo(payment_reference=p.charge_id)
        self.assertIn("Possible WooCommerce",classify(p)[0])

    def test_direct_review_exact_and_protected(self):
        p=self.payment()
        url=reverse("accounting:stripe_review",args=[p.pk])
        self.assertContains(self.client.get(url),"Complete sale details")
        self.assertEqual(self.client.post(url,self.form()).status_code,302)
        p.refresh_from_db()
        self.assertEqual(p.review_data["state"],"reviewed")
        self.assertEqual(p.gross,Decimal("16.53"))
        self.assertEqual(len(p.review_history),1)
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())

    def test_bad_allocation_and_email(self):
        p=self.payment()
        url=reverse("accounting:stripe_review",args=[p.pk])
        self.assertContains(self.client.post(url,self.form(unit_price="16.52")),"must equal")
        self.assertContains(self.client.post(url,self.form(customer_email="other@example.com")),"Keep the imported")
        p.refresh_from_db()
        self.assertEqual(p.review_data,{})

    def test_woo_cannot_review_direct(self):
        p=self.payment(**{"order_id (metadata)":"123"})
        self.woo()
        self.assertEqual(self.client.post(reverse("accounting:stripe_review",args=[p.pk]),self.form()).status_code,400)

    def test_exclude_restore_history(self):
        p=self.payment()
        url=reverse("accounting:stripe_review",args=[p.pk])
        self.assertEqual(self.client.post(url,{"action":"exclude","reason":"Personal test","confirm":"yes"}).status_code,302)
        p.refresh_from_db()
        self.assertEqual(p.review_data["state"],"excluded")
        self.assertEqual(self.client.post(url,self.form()).status_code,400)
        self.assertEqual(self.client.post(url,{"action":"restore","confirm":"yes"}).status_code,302)
        p.refresh_from_db()
        self.assertEqual(p.review_data,{})
        self.assertEqual(len(p.review_history),2)

    def test_customer_existing_requires_selection(self):
        p=self.payment()
        c=Customer.objects.create(name="Buyer",email="buyer@example.com")
        url=reverse("accounting:stripe_review",args=[p.pk])
        self.assertContains(self.client.post(url,self.form()),"Select the existing")
        self.assertEqual(self.client.post(url,self.form(customer=str(c.pk))).status_code,302)

    def test_nonstaff(self):
        p=self.payment()
        self.client.force_login(get_user_model().objects.create_user(username="ordinary"))
        self.assertEqual(self.client.post(reverse("accounting:stripe_review",args=[p.pk]),self.form()).status_code,302)
        p.refresh_from_db()
        self.assertEqual(p.review_data,{})
