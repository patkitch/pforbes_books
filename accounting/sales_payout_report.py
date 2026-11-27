"""Read-only staged sales report; one row per sale, never per processor charge."""
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zoneinfo import ZoneInfo
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from accounting.models import Account
from accounting_contacts.models import Receipt
from accounting_imports.models import WooOrderImport, StripePaymentImport, WooPayoutMatch, StripePayoutMatch
from accounting_imports.woo_payouts import eligible_order, paid_date, processor_for, metadata_money
from accounting_imports.stripe_imports import classify

ZERO = Decimal("0.00")
MONEY = ("artwork", "shipping", "tax", "gross", "fee", "net", "deposit")
HEADERS = ("Sale date", "Customer", "Source", "Reference", "Artwork / item", "Shipping", "Sales tax", "Gross", "Fee", "Expected net", "Bank deposit", "Deposit date", "Bank account", "Status", "Receipt")
KEYS = ("day", "customer", "source", "reference", *MONEY, "deposit_date", "bank", "status", "receipt")


class ReportFilters(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date"}), label="Sale date from")
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type":"date"}), label="Sale date through")
    source = forms.ChoiceField(required=False, choices=[("", "All sources"), ("woo","WooCommerce"), ("stripe","Direct Stripe")])
    def clean(self):
        data = super().clean()
        if data.get("start") and data.get("end") and data["start"] > data["end"]:
            raise forms.ValidationError("Start date must not be after end date.")
        return data


def money(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number >= 0 and number == number.quantize(Decimal("0.01")) else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def build_report(start=None, end=None, source=""):
    rows = []
    omitted = 0
    accounts = {a.pk:str(a) for a in Account.objects.all()}
    woo_matches = {m.order_id:m for m in WooPayoutMatch.objects.filter(undone_at__isnull=True).select_related("bank_row")}
    stripe_matches = {m.payment_id:m for m in StripePayoutMatch.objects.filter(undone_at__isnull=True).select_related("bank_row")}
    linked = {}
    direct = []
    for p in StripePaymentImport.objects.all():
        label, order = classify(p)
        if label == "WooCommerce linked — no new sale":
            linked.setdefault(order.pk, []).append(p)
        elif label == "Possible direct sale — review required" and p.review_data.get("state") == "reviewed" and p.currency.upper()=="USD":
            direct.append(p)
        elif p.review_data.get("state") != "excluded":
            omitted += 1
    def add(row, match):
        if (start and row["day"] < start) or (end and row["day"] > end):
            return
        row.update(deposit=None, deposit_date=None, bank="", status="Unmatched")
        if match:
            row.update(deposit=match.bank_row.amount, deposit_date=match.bank_row.transaction_date,
                       bank=accounts.get(match.bank_row.account_id, f"Account #{match.bank_row.account_id}"),
                       status="Matched — not posted")
            if match.gross != row["gross"] or match.net != match.bank_row.amount or match.gross-match.fee != match.net or (row["fee"] is not None and row["fee"] != match.fee):
                row["status"]="Conflict — review"
            else:
                row.update(fee=match.fee, net=match.net)
        if row["fee"] is not None and row["fee"] > row["gross"]:
            row.update(fee=None,net=None,status="Conflict — review")
        rows.append(row)
    if source != "stripe":
        for o in WooOrderImport.objects.all():
            if not eligible_order(o) or o.total < o.shipping_total+o.tax_total or min(o.shipping_total,o.tax_total)<0:
                continue
            charges = linked.get(o.pk,[])
            fee = charges[0].fee if len(charges)==1 else metadata_money(o,("_stripe_fee","Stripe Fee")) if processor_for(o)=="Stripe" else None
            add(dict(day=paid_date(o),customer=o.customer_name or "Name not provided",source="WooCommerce",
                reference=f"Order #{o.source_order_id}",artwork=o.total-o.shipping_total-o.tax_total,shipping=o.shipping_total,tax=o.tax_total,gross=o.total,
                fee=fee,net=o.total-fee if fee is not None else None,receipt=o.receipt_id,
                detail=reverse("accounting:woo_payout",args=[o.pk])),woo_matches.get(o.pk))
    if source != "woo":
        receipts={r.source_reference:r for r in Receipt.objects.filter(source="stripe_direct").select_related("customer")}
        for p in direct:
            r=receipts.get(p.charge_id)
            data=p.review_data
            shipping,tax,price=(money(data.get(k)) for k in ("shipping","tax","unit_price"))
            try:
                qty=int(data.get("quantity"))
            except (ValueError,TypeError):
                qty=0
            if None in (shipping,tax,price) or qty<1 or price*qty+shipping+tax!=p.gross:
                omitted+=1
                continue
            day=p.created_utc.astimezone(ZoneInfo("America/Chicago")).date()
            add(dict(day=day,customer=(r.customer.name if r and r.customer else "") or data.get("customer_name") or p.customer_name or "Name not provided",
                source="Direct Stripe",reference=p.charge_id,artwork=price*qty,shipping=shipping,tax=tax,gross=p.gross,
                fee=p.fee,net=p.gross-p.fee,receipt=r.pk if r else None,detail=reverse("accounting:stripe_payout",args=[p.pk])),stripe_matches.get(p.pk))
    rows.sort(key=lambda r:(r["day"],r["source"],r["reference"]))
    totals={k:sum((r[k] for r in rows if r[k] is not None),ZERO) for k in MONEY}
    incomplete={k:sum(r[k] is None for r in rows) for k in MONEY}
    matched=[r for r in rows if r["status"]=="Matched — not posted"]
    difference=sum((r["net"]-r["deposit"] for r in matched),ZERO)
    return dict(rows=rows, totals=totals, incomplete=incomplete, difference=difference, matched_count=len(matched), omitted=omitted)


def export_rows(report):
    yield HEADERS
    for r in report["rows"]:
        yield tuple(r[k] for k in KEYS)
    yield ("TOTAL (known amounts)",None,None,None,*(report["totals"][k] for k in MONEY),None,None,None,None)


def xlsx(report, caption):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb=Workbook()
    ws=wb.active
    ws.title="Sales and payouts"
    ws.append(["P. Forbes Art — Sales and Payout Reconciliation"])
    ws.append([caption])
    ws.append(["Review only — not a ledger report. Blank = unknown or not matched."])
    ws.append(["Known amounts only; omitted or unresolved payments are not included."])
    for values in export_rows(report):
        ws.append(list(values))
        for cell in ws[ws.max_row]:
            if isinstance(cell.value,str):
                cell.data_type="s"
            elif isinstance(cell.value,Decimal):
                cell.number_format='#,##0.00'
            elif isinstance(cell.value,date):
                cell.number_format="yyyy-mm-dd"
    for cell in ws[5]:
        cell.font=Font(bold=True,color="FFFFFF")
        cell.fill=PatternFill("solid",fgColor="19516D")
    for cell in ws[ws.max_row]:
        cell.font=Font(bold=True)
    ws.freeze_panes="E6"
    ws.auto_filter.ref=f"A5:O{max(5,ws.max_row-1)}"
    for i,width in enumerate([24,26,19,42,16,14,14,14,14,16,16,16,32,28,14],1):
        ws.column_dimensions[get_column_letter(i)].width=width
    ws.append(["Matched rows",report["matched_count"],"Matched difference",report["difference"]])
    ws.append(["Missing fee",report["incomplete"]["fee"],"Missing deposit",report["incomplete"]["deposit"]])
    buf=BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf(report, caption):
    from fpdf import FPDF
    doc=FPDF(format="letter")
    doc.set_auto_page_break(auto=True,margin=15)
    doc.add_page()
    def line(s,bold=False):
        doc.set_x(doc.l_margin)
        doc.set_font("Helvetica","B" if bold else "",10)
        doc.multi_cell(0,5,str(s).replace("—","-").encode("latin-1","replace").decode("latin-1"))
    def amt(v):
        return "Unknown" if v is None else f"${v:,.2f}"
    line("P. Forbes Art | Sales and Payout Reconciliation",True)
    line(caption)
    line("Review only - not a ledger report. Totals include known amounts only.")
    for r in report["rows"]:
        doc.ln(3)
        line(f"{r['day']} | {r['customer']} | {r['source']}",True)
        line(f"{r['reference']} | Receipt {r['receipt'] or 'Not created'}")
        line(f"Artwork {amt(r['artwork'])} | Shipping {amt(r['shipping'])} | Tax {amt(r['tax'])} | Gross {amt(r['gross'])}")
        line(f"Fee {amt(r['fee'])} | Expected net {amt(r['net'])} | Bank deposit {amt(r['deposit'])}")
        line(f"{r['status']} | {r['deposit_date'] or '-'} | {r['bank'] or '-'}")
    doc.ln(4)
    line("Totals (known amounts)",True)
    for k in MONEY:
        line(f"{k.title()}: {amt(report['totals'][k])} | Missing: {report['incomplete'][k]}")
    line(f"Matched rows: {report['matched_count']} | Matched difference: {amt(report['difference'])}")
    return bytes(doc.output())


@staff_member_required(login_url="/admin/login/")
def sales_payout_report(request):
    form=ReportFilters(request.GET or {})
    if not form.is_valid():
        if request.GET.get("format"):
            return HttpResponseBadRequest("Invalid report filters.")
        return render(request,"accounting/sales_payout_report.html",{"form":form})
    data=form.cleaned_data
    report=build_report(**data)
    fmt=request.GET.get("format")
    caption=f"Sale dates: {data['start'] or 'All'} through {data['end'] or 'All'} | Source: {dict(form.fields['source'].choices).get(data['source'],'All sources')}"
    if fmt:
        if fmt=="xlsx":
            content,ctype=xlsx(report,caption),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt=="pdf":
            content,ctype=pdf(report,caption),"application/pdf"
        else:
            return HttpResponseBadRequest("Unknown format.")
        response=HttpResponse(content,content_type=ctype)
        response["Content-Disposition"]=f'attachment; filename="sales_payout_reconciliation.{fmt}"'
        response["Cache-Control"]="no-store"
        return response
    params=request.GET.copy()
    params.pop("format",None)
    response=render(request,"accounting/sales_payout_report.html",{"form":form,"report":report,"query":params.urlencode(),"caption":caption})
    response["Cache-Control"]="no-store"
    return response
