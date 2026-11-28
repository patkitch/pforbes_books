"""Explicit local import posting. All entries use the core balanced journal service."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from accounting.models import Account, JournalEntry, JournalLine
from accounting.services import post_entry
from accounting.period_controls import ensure_open_period, LEDGER_START
from accounting.import_preview import eligible_import_accounts
from accounting_contacts.models import Receipt, Vendor
from accounting_contacts.services import link_contact
from .models import ImportRow, WooOrderImport, StripePaymentImport, WooPayoutMatch, StripePayoutMatch, StripeGroupMatch, CardPaymentMatch, StripeAdjustment
from .stripe_imports import classify
from .woo_payouts import eligible_order, paid_date, processor_for, metadata_money
from .stripe_adjustments import active_adjustments
from .payment_matching import active_match

ZERO=Decimal("0.00")
EXPENSE=("expense","cogs","other_expense")
INCOME=("income","other_income")
SOURCE="reviewed_import"

def fail(message):
    raise ValidationError(message)

def money(value):
    try:
        v=Decimal(str(value))
        if not v.is_finite() or v!=v.quantize(Decimal(".01")) or abs(v)>=Decimal("1000000000000"):
            raise ValueError
        return v
    except (ValueError,TypeError,InvalidOperation):
        fail("Invalid saved currency amount.")

def account(pk,types):
    a=Account.objects.filter(pk=pk,is_active=True,account_type__in=types).first() if pk else None
    if not a or a.children.exists():
        fail("Choose an active posting account of the appropriate type (not a subtotal parent).")
    return a

def bank_account(row):
    if not eligible_import_accounts().filter(pk=row.account_id).exists():
        fail("Invalid imported financial account.")
    return account(row.account_id,("asset","liability"))

def existing(key):
    return JournalEntry.objects.filter(source=SOURCE,source_reference=key).first()

def row_posted(pk):
    return existing("bank:"+str(pk)) is not None or ImportRow.objects.filter(pk=pk,status="posted").exists()

def sale_posted(kind,pk):
    return existing(kind+":"+str(pk)) is not None

def payment_posted(p):
    return sale_posted("stripe",p.pk) or bool(p.woo_order_number and WooOrderImport.objects.filter(source_order_id=p.woo_order_number).exists() and sale_posted("woo",WooOrderImport.objects.get(source_order_id=p.woo_order_number).pk))

@dataclass
class Plan:
    key:str
    day:date
    label:str
    lines:list=field(default_factory=list)
    vendor:object=None
    customer:object=None
    receipts:list=field(default_factory=list)
    rows:list=field(default_factory=list)
    memo:str=""
    def line(self,a,signed):
        v=money(signed)
        if v:
            self.lines.append((a,max(v,ZERO),max(-v,ZERO)))
    def check(self):
        if existing(self.key):
            fail("Source already posted; use journal correction, not reposting.")
        if self.day<LEDGER_START:
            fail("Transaction predates the test ledger.")
        ensure_open_period(self.day)
        if len(self.lines)<2 or sum((d-c for a,d,c in self.lines),ZERO)!=0:
            fail("Proposed journal is not balanced.")
        if any(row_posted(r.pk) for r in self.rows):
            fail("Financial source already consumed.")
        if any(r.journal_entry_id for r in self.receipts):
            fail("Receipt is already linked to a journal entry.")
        return self

def lock(qs,enabled):
    return qs.select_for_update() if enabled else qs

def clearing(cfg,processor):
    a=account(cfg.get("stripe_clearing" if processor=="Stripe" else "woo_clearing"),("asset",))
    if eligible_import_accounts().filter(pk=a.pk).exists():
        fail("Processor clearing must be a separate non-bank asset account.")
    return a

def sale_receipt(p,kind,pk):
    if kind=="woo":
        r=Receipt.objects.filter(pk=p.receipt_id,source="woocommerce",source_reference="order:"+str(p.source_order_id),amount=p.total).select_related("customer").first()
    else:
        r=Receipt.objects.filter(pk=p.review_data.get("receipt_id"),source="stripe_direct",source_reference=p.charge_id,amount=p.gross).select_related("customer").first()
    if not r or not r.customer or not r.customer.is_active:
        fail("Create the internal sales receipt with a verified active customer first.")
    return r

def sale_plan(kind,pk,cfg,locked=False):
    if kind=="woo":
        o=lock(WooOrderImport.objects,locked).get(pk=pk)
        if not eligible_order(o):
            fail("Order is not an eligible paid USD sale.")
        r=sale_receipt(o,kind,pk)
        gross,ship,tax=o.total,o.shipping_total,o.tax_total
        processor=processor_for(o)
        day=paid_date(o)
        revenue=account(cfg.get("website_revenue"),INCOME)
        shipping=account(cfg.get("shipping_income"),INCOME) if ship else None
        authority=account(cfg.get("tax_payable"),("liability",)) if tax else None
        charges=list(StripePaymentImport.objects.filter(Q(woo_order_number=o.source_order_id)|Q(charge_id=o.payment_reference))) if processor=="Stripe" else []
        if any(classify(p)[0]!="WooCommerce linked — no new sale" or classify(p)[1].pk!=o.pk for p in charges) or len(charges)>1:
            fail("Resolve original payment association first.")
        match=o.payout_matches.filter(undone_at__isnull=True).first()
        member=o.stripe_group_memberships.filter(group__undone_at__isnull=True).first()
        candidates=[x for x in (charges[0].fee if charges else None,metadata_money(o,("_stripe_fee","Stripe Fee")) if processor=="Stripe" else None,match.fee if match else None,member.fee if member else None) if x is not None]
        if not candidates or len(set(candidates))!=1:
            fail("Processing fee missing or conflicting; verify processor detail first.")
        fee=candidates[0]
        label="WooCommerce order #"+str(o.source_order_id)
    else:
        p=lock(StripePaymentImport.objects,locked).get(pk=pk)
        if classify(p)[0]!="Possible direct sale — review required" or p.review_data.get("state")!="reviewed" or p.currency.upper()!="USD":
            fail("Direct payment is not an eligible reviewed business sale.")
        r=sale_receipt(p,kind,pk)
        data=p.review_data
        gross,ship,tax=p.gross,money(data.get("shipping")),money(data.get("tax"))
        if money(data.get("unit_price"))*int(data.get("quantity",0))+ship+tax!=gross:
            fail("Direct sale allocation mismatch.")
        revenue=account(data.get("revenue"),INCOME)
        shipping=account(data.get("shipping_account"),INCOME) if ship else None
        authority=account(data.get("tax_account"),("liability",)) if tax else None
        processor="Stripe"
        day=p.created_utc.astimezone(ZoneInfo("America/Chicago")).date()
        fee=p.fee
        label="Direct Stripe "+p.charge_id
    if min(gross,ship,tax,fee)<0 or ship+tax>gross or fee>=gross:
        fail("Sale amount or fee invalid.")
    if authority and eligible_import_accounts().filter(pk=authority.pk).exists():
        fail("Sales tax cannot be posted to a credit card account.")
    clear=clearing(cfg,processor)
    plan=Plan(kind+":"+str(pk),day,label,customer=r.customer,receipts=[r])
    plan.line(clear,gross-fee)
    plan.line(revenue,-(gross-ship-tax))
    if ship: plan.line(shipping,-ship)
    if tax: plan.line(authority,-tax)
    if fee: plan.line(account(cfg.get("processor_fee"),EXPENSE),fee)
    return plan.check()

def bank_plan(pk,cfg,locked=False):
    row=lock(ImportRow.objects,locked).get(pk=pk)
    if row.status!=ImportRow.REVIEWED or row.batch.undone_at:
        fail("Bank transaction must be reviewed first.")
    if row.woo_payout_matches.filter(undone_at__isnull=True).exists() or row.stripe_payout_matches.filter(undone_at__isnull=True).exists() or row.stripe_group_matches.filter(undone_at__isnull=True).exists():
        fail("Use payout posting rather than ordinary bank posting.")
    a=bank_account(row)
    d=row.review_data
    kind=d.get("classification")
    n=abs(row.amount)
    plan=Plan("bank:"+str(pk),row.transaction_date,row.description,rows=[row],memo=d.get("memo",""))
    if kind in ("expense","split","vendor_credit"):
        v=Vendor.objects.filter(pk=d.get("vendor"),is_active=True).first()
        if not v: fail("Select an active vendor.")
        plan.vendor=v
        if kind=="vendor_credit":
            if row.amount<=0: fail("Vendor credit must be positive.")
            plan.line(a,n)
            plan.line(account(d.get("category"),EXPENSE),-n)
        elif kind=="expense":
            if row.amount>=0: fail("Expense must be negative.")
            plan.line(account(d.get("category"),EXPENSE),n)
            plan.line(a,-n)
        else:
            if row.amount>=0: fail("Split purchase must be negative.")
            splits=d.get("splits",[])
            if sum((money(s.get("amount")) for s in splits),ZERO)!=n:
                fail("Split does not equal source amount.")
            business=ZERO
            for s in splits:
                value=money(s.get("amount"))
                if value<=0 or s.get("kind") not in ("business","personal"): fail("Invalid split.")
                if s["kind"]=="business":
                    plan.line(account(s.get("category"),EXPENSE),value)
                    business+=value
            if not business: fail("No business expense.")
            plan.line(a,-business)
        plan.receipts=list(Receipt.objects.filter(source="bank_document",source_reference__startswith=str(pk)+":"))
        if d.get("receipt"):
            r=Receipt.objects.filter(pk=d["receipt"]).first()
            if not r: fail("Linked receipt is missing.")
            if r not in plan.receipts: plan.receipts.append(r)
        if any(r.vendor_id!=v.pk for r in plan.receipts): fail("Receipt vendor mismatch.")
    elif kind=="income":
        if row.amount<=0 or a.account_type!="asset": fail("Income requires a positive bank deposit.")
        if "stripe" in row.description.casefold() or "woopayments" in row.description.casefold(): fail("Processor deposits must use payout reconciliation.")
        plan.line(a,n)
        plan.line(account(d.get("category"),INCOME),-n)
    elif kind=="gallery":
        gross,fee=money(d.get("gallery_gross")),money(d.get("gallery_commission"))
        if a.account_type!="asset" or row.amount<=0 or gross-fee!=row.amount or fee<0: fail("Gallery allocation mismatch.")
        plan.day=date.fromisoformat(d["gallery_received"])
        if plan.day>row.transaction_date: fail("Invalid gallery receipt date.")
        plan.label=d.get("gallery_name") or "Gallery deposit"
        plan.line(a,n)
        plan.line(account(d.get("gallery_income"),INCOME),-gross)
        if fee: plan.line(account(d.get("gallery_commission_account"),EXPENSE),fee)
    elif kind=="card_payment":
        match=active_match(pk).first()
        if a.account_type!="asset" or row.amount>=0 or not match or match.bank_row_id!=pk:
            fail("Match both bank and card sides before posting.")
        card=lock(ImportRow.objects,locked).get(pk=match.card_row_id)
        target=bank_account(card)
        portion=money(d.get("payment_business"))
        if target.account_type!="liability" or target.pk!=d.get("payment_card") or card.amount!=n or not ZERO<portion<=n: fail("Card payment allocation mismatch.")
        plan.rows.append(card)
        plan.line(target,portion)
        if d.get("payment_funding")=="personal":
            plan.line(account(d.get("payment_equity"),("equity",)),-portion)
        elif d.get("payment_funding")=="business":
            plan.line(a,-portion)
        else: fail("Funding source missing.")
    elif kind in ("owner_contribution","owner_draw"):
        if a.account_type!="asset" or (kind=="owner_contribution" and row.amount<=0) or (kind=="owner_draw" and row.amount>=0):
            fail("Owner transaction direction invalid.")
        plan.line(a,row.amount)
        plan.line(account(d.get("category"),("equity",)),-row.amount)
    elif kind=="transfer":
        if a.account_type!="asset" or row.amount>=0: fail("Select outgoing bank transfer.")
        other=lock(ImportRow.objects,locked).filter(pk=d.get("transfer_row")).first()
        if not other or other.status!=ImportRow.PENDING or other.amount!=n or abs((other.transaction_date-row.transaction_date).days)>7 or other.account_id==a.pk or other.review_data or active_match(other.pk).exists() or other.woo_payout_matches.filter(undone_at__isnull=True).exists() or other.stripe_payout_matches.filter(undone_at__isnull=True).exists() or other.stripe_group_matches.filter(undone_at__isnull=True).exists():
            fail("Transfer counterpart unavailable or not an exact match.")
        target=bank_account(other)
        if target.account_type!="asset": fail("Transfer requires two bank accounts.")
        plan.rows.append(other)
        plan.line(target,n)
        plan.line(a,-n)
    else: fail("Unsupported or unresolved bank classification.")
    if kind!="card_payment" and active_match(pk).exists(): fail("Source already belongs to a card payment.")
    return plan.check()

def payout_plan(pk,cfg,locked=False):
    row=lock(ImportRow.objects,locked).get(pk=pk)
    if row.status!=ImportRow.PENDING or row.batch.undone_at or row.amount<=0: fail("Deposit unavailable.")
    a=bank_account(row)
    if a.account_type!="asset": fail("Payout requires a bank account.")
    matches=[]
    for model in (WooPayoutMatch,StripePayoutMatch,StripeGroupMatch):
        matches.extend(list(model.objects.filter(bank_row=row,undone_at__isnull=True)))
    if len(matches)!=1: fail("Exactly one verified payout match is required.")
    m=matches[0]
    processor=m.processor if isinstance(m,WooPayoutMatch) else "Stripe"
    clear=clearing(cfg,processor)
    if isinstance(m,WooPayoutMatch):
        sources=[("woo",m.order_id,m.net)]
    elif isinstance(m,StripePayoutMatch):
        sources=[("stripe",m.payment_id,m.net)]
    else:
        sources=[("woo" if x.order_id else "stripe",x.order_id or x.payment_id,x.net) for x in m.members.all()]
    if sum((n for k,i,n in sources),ZERO)!=row.amount or m.net!=row.amount or m.gross-m.fee!=m.net:
        fail("Payout totals do not balance.")
    for kind,i,n in sources:
        entry=existing(kind+":"+str(i))
        if not entry or entry.status!="posted" or entry.reversed_by_entry_id or entry.date>row.transaction_date:
            fail("Post all constituent sales first.")
        if sum((l.debit-l.credit for l in entry.lines.filter(account=clear)),ZERO)!=n:
            fail("Sale clearing amount or account differs from payout.")
    plan=Plan("bank:"+str(pk),row.transaction_date,"Processor payout — "+row.description,rows=[row],memo=m.evidence)
    plan.line(a,row.amount)
    plan.line(clear,-row.amount)
    return plan.check()

def adjustment_plan(pk,cfg,locked=False):
    a=lock(StripeAdjustment.objects,locked).get(pk=pk)
    if a.voided_at: fail("Adjustment is voided.")
    clear=clearing(cfg,"Stripe")
    plan=Plan("adjustment:"+str(pk),a.day,a.get_kind_display()+" "+a.balance_id,memo=a.evidence)
    if a.kind=="refund":
        p=a.payment
        if not p: fail("Original sale is missing.")
        if p.woo_order_number:
            o=WooOrderImport.objects.filter(source_order_id=p.woo_order_number).first()
            if not o: fail("Original WooCommerce order missing.")
            entry=existing("woo:"+str(o.pk))
            r=sale_receipt(o,"woo",o.pk)
            revenue=account(cfg.get("website_revenue"),INCOME)
            shipping=account(cfg.get("shipping_income"),INCOME) if a.shipping else None
            tax=account(cfg.get("tax_payable"),("liability",)) if a.tax else None
        else:
            entry=existing("stripe:"+str(p.pk))
            r=sale_receipt(p,"stripe",p.pk)
            revenue=account(p.review_data.get("revenue"),INCOME)
            shipping=account(p.review_data.get("shipping_account"),INCOME) if a.shipping else None
            tax=account(p.review_data.get("tax_account"),("liability",)) if a.tax else None
        if not entry or entry.status!="posted" or entry.reversed_by_entry_id or entry.date>a.day: fail("Post original sale first.")
        if not entry.lines.filter(account=clear,debit__gt=0).exists(): fail("Original clearing account differs.")
        for acct,value in ((revenue,a.artwork),(shipping,a.shipping),(tax,a.tax)):
            if value:
                if not entry.lines.filter(account=acct,credit__gt=0).exists(): fail("Refund account differs from original sale.")
                plan.line(acct,value)
        plan.customer=r.customer
    if a.fee: plan.line(account(cfg.get("processor_fee"),EXPENSE),a.fee)
    plan.line(clear,a.net)
    return plan.check()

def build(key,cfg,locked=False):
    try:
        kind,raw=key.split(":")
        pk=int(raw)
        if pk<=0: raise ValueError
        if kind in ("woo","stripe"): return sale_plan(kind,pk,cfg,locked)
        if kind=="bank": return bank_plan(pk,cfg,locked)
        if kind=="payout": return payout_plan(pk,cfg,locked)
        if kind=="adjustment": return adjustment_plan(pk,cfg,locked)
    except (ValueError,TypeError,KeyError,ImportRow.DoesNotExist,WooOrderImport.DoesNotExist,StripePaymentImport.DoesNotExist,StripeAdjustment.DoesNotExist):
        fail("Invalid or unavailable source record.")
    fail("Unknown source.")

def write(plan,actor):
    plan.check()
    entry=JournalEntry.objects.create(date=plan.day,payee=(plan.customer.name if plan.customer else plan.vendor.name if plan.vendor else "")[:200],description=plan.label[:255],memo=plan.memo,source=SOURCE,source_reference=plan.key,created_by=actor)
    for a,d,c in plan.lines:
        JournalLine.objects.create(entry=entry,account=a,debit=d,credit=c)
    if plan.vendor or plan.customer:
        link_contact(entry,vendor=plan.vendor,customer=plan.customer,actor=actor)
    entry=post_entry(entry.pk,actor=actor)
    for r in plan.receipts:
        r.journal_entry_id=entry.pk
        r.save(update_fields=["journal_entry_id"])
    for row in plan.rows:
        row.status="posted"
        row.save(update_fields=["status"])
    return entry

@transaction.atomic
def post_selected(keys,cfg,actor):
    # Sales precede adjustments and settlements. A failed selection rolls back the whole batch.
    entries=[]
    for key in sorted(set(keys),key=lambda k:{"woo":0,"stripe":0,"bank":1,"adjustment":2,"payout":3}.get(k.split(":")[0],9)):
        entries.append(write(build(key,cfg,True),actor))
    return entries
