from datetime import date,datetime,timezone
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from accounting.models import Account,JournalEntry
from accounting_contacts.models import Vendor,Customer,Receipt,TransactionParty
from .models import ImportRow,ImportBatch,WooOrderImport,WooPayoutMatch
from .posting import build,post_selected

class PostingTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="poster",is_staff=True)
        self.client.force_login(self.user)
        self.bank=Account.objects.create(number="1002",name="Checking",account_type="asset")
        self.clear=Account.objects.create(number="1099",name="Stripe clearing",account_type="asset")
        self.rev=Account.objects.create(number="4014",name="Website Sales",account_type="income")
        self.fee=Account.objects.create(number="6001",name="Processing fee",account_type="expense")
        self.tax=Account.objects.create(number="2007",name="Sales tax payable",account_type="liability")
        self.vendor=Vendor.objects.create(name="Printer")
        self.batch=ImportBatch.objects.create(account_id=self.bank.pk,filename="bank.csv")
        self.cfg={"stripe_clearing":self.clear.pk,"website_revenue":self.rev.pk,"processor_fee":self.fee.pk,"tax_payable":self.tax.pk}
        self.day=date(2026,10,4)
    def row(self,amount,desc="Expense",review=None):
        return ImportRow.objects.create(batch=self.batch,account_id=self.bank.pk,transaction_date=self.day,description=desc,amount=amount,fingerprint=str(ImportRow.objects.count()).zfill(64),status="reviewed" if review else "pending",review_data=review or {})
    def expense(self):
        return self.row(-25,review={"classification":"expense","vendor":self.vendor.pk,"category":self.fee.pk})
    def test_expense_contact_and_duplicate(self):
        r=self.expense()
        e=post_selected(["bank:"+str(r.pk)],self.cfg,self.user)[0]
        self.assertEqual(e.status,"posted")
        self.assertEqual(e.lines.get(account=self.fee).debit,25)
        self.assertEqual(TransactionParty.objects.get(journal_entry_id=e.pk).vendor,self.vendor)
        r.refresh_from_db()
        self.assertEqual(r.status,"posted")
        with self.assertRaises(ValidationError): post_selected(["bank:"+str(r.pk)],self.cfg,self.user)
        self.assertEqual(self.client.post(reverse("accounting:import_status",args=[r.pk]),{"status":"excluded"}).status_code,400)
    def test_preview_approval(self):
        r=self.expense()
        url=reverse("accounting:posting_center")
        response=self.client.post(url,{"action":"preview","selected":"bank:"+str(r.pk),**self.cfg})
        self.assertTrue(response.context["token"])
        self.assertFalse(JournalEntry.objects.exists())
        r.refresh_from_db()
        self.assertEqual(r.status,"reviewed")
        response=self.client.post(url,{"action":"post","token":response.context["token"],"confirm":"yes"})
        self.assertEqual(len(response.context["result"]),1)
    def test_rollback(self):
        r=self.expense()
        bad=self.row(-1,review={"classification":"deferred"})
        with self.assertRaises(ValidationError): post_selected(["bank:"+str(r.pk),"bank:"+str(bad.pk)],self.cfg,self.user)
        self.assertFalse(JournalEntry.objects.exists())
    def test_sale_and_payout(self):
        c=Customer.objects.create(name="Buyer")
        receipt=Receipt.objects.create(customer=c,title="Sale",source="woocommerce",source_reference="order:88",receipt_type="sale",date=self.day,amount=106)
        o=WooOrderImport.objects.create(source_order_id=88,order_date=self.day,woo_status="completed",total=106,tax_total=6,payment_method="Stripe",review_status="receipted",receipt_id=receipt.pk,payload={"currency":"USD","date_paid":"2026-10-04T12:00:00","payment_method":"stripe"})
        r=self.row(103,"Stripe")
        WooPayoutMatch.objects.create(order=o,bank_row=r,processor="Stripe",gross=106,fee=3,net=103,evidence="Verified")
        entries=post_selected(["payout:"+str(r.pk),"woo:"+str(o.pk)],self.cfg,self.user)
        self.assertEqual(len(entries),2)
        self.assertEqual(entries[0].lines.get(account=self.rev).credit,100)
        self.assertEqual(entries[0].lines.get(account=self.tax).credit,6)
        self.assertEqual(entries[0].lines.get(account=self.clear).debit,103)
        self.assertEqual(entries[1].lines.get(account=self.clear).credit,103)
        receipt.refresh_from_db()
        self.assertEqual(receipt.journal_entry_id,entries[0].pk)
    def test_vendor_credit(self):
        r=self.row(7,review={"classification":"vendor_credit","vendor":self.vendor.pk,"category":self.fee.pk})
        e=post_selected(["bank:"+str(r.pk)],self.cfg,self.user)[0]
        self.assertEqual(e.lines.get(account=self.fee).credit,7)
