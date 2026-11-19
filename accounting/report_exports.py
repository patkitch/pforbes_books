"""Downloadable financial statements using the existing fpdf2 dependency and
standard-library Office Open XML writing (no additional packages)."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, HttpResponseBadRequest

from .report_views import BalanceSheetDate, ProfitLossDates, default_balance_sheet_date, default_profit_loss_dates
from .reporting import balance_sheet, profit_and_loss


def report_rows(kind, report):
    """Use the exact same calculated groups and subtotals as the browser reports."""
    rows = [("P. Forbes Art", None)]
    if kind == "pl":
        rows += [("Profit & Loss", None), (
            f"From {report['start'].isoformat()} through {report['end'].isoformat()}", None
        )]
    else:
        rows += [("Balance Sheet", None), (f"As of {report['as_of'].isoformat()}", None)]
    rows.append(("Posted transactions only — 2026-start local test ledger", None))
    rows.append(("", None))
    for group in report["groups"]:
        rows.append((group["title"], None))
        for entry in group["rows"]:
            account = entry["account"]
            rows.append((f"{account.number} — {account.name}", entry["amount"]))
        if kind == "bs" and group["key"] == "equity":
            rows.append(("Accumulated earnings", report["earnings"]))
            rows.append(("Total Equity including earnings", report["total_equity"]))
        else:
            rows.append((f"Total {group['title']}", group["total"]))
        if kind == "pl" and group["key"] == "cogs":
            rows.append(("Gross profit", report["gross_profit"]))
        if kind == "pl" and group["key"] == "expense":
            rows.append(("Operating profit", report["operating_profit"]))
        rows.append(("", None))
    if kind == "pl":
        rows.append(("Net profit / loss", report["net_profit"]))
    else:
        rows += [
            ("Total Liabilities + Equity", report["liabilities_and_equity"]),
            ("Assets less Liabilities and Equity", report["difference"]),
            ("Balance Sheet balances" if report["balanced"] else "WARNING: Balance Sheet does not balance", None),
        ]
    return rows


def make_xlsx(rows):
    """Single-sheet XLSX with numeric amount cells and a two-decimal display format."""
    def col_name(num):
        name = ""
        while num:
            num, digit = divmod(num - 1, 26)
            name = chr(65 + digit) + name
        return name

    cells = []
    for idx, (label, amount) in enumerate(rows, start=1):
        ref = f"A{idx}"
        safe = escape(str(label), {'"': "&quot;", "'": "&apos;"})
        cells.append(f'<row r="{idx}"><c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{safe}</t></is></c>')
        if amount is not None:
            cells.append(f'<c r="B{idx}" s="1"><v>{Decimal(amount):.2f}</v></c>')
        cells.append("</row>")
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="68" customWidth="1"/>'
        '<col min="2" max="2" width="20" customWidth="1"/></cols>'
        '<sheetData>' + "".join(cells) + '</sheetData></worksheet>'
    )
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
                ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Financial Statement" sheetId="1" r:id="rId1"/></sheets></workbook>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
              '<borders count="1"><border/></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2">'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
              '</cellXfs></styleSheet>')
    files = {
        '[Content_Types].xml': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        ),
        '_rels/.rels': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ),
        'xl/_rels/workbook.xml.rels': (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        ),
        'xl/workbook.xml': workbook,
        'xl/styles.xml': styles,
        'xl/worksheets/sheet1.xml': worksheet,
    }
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    return buffer.getvalue()


def make_pdf(rows):
    from fpdf import FPDF

    doc = FPDF(format="letter")
    doc.set_auto_page_break(auto=True, margin=18)
    doc.add_page()
    doc.set_margins(18, 18, 18)
    for index, (label, amount) in enumerate(rows):
        # fpdf2's multi_cell may leave the cursor at the right edge.
        # Always begin the next report row at the left page margin.
        doc.set_x(doc.l_margin)
        if not label and amount is None:
            doc.ln(4)
            continue
        prominent = (index in (0, 1)) or label.startswith("Total ") or label in {
            "Gross profit", "Operating profit", "Net profit / loss",
        }
        doc.set_font("Helvetica", "B" if prominent else "", 12 if index == 1 else 10)
        if prominent:
            doc.set_fill_color(237, 243, 247)
        normalized = label.replace("—", "-").replace("–", "-").encode("latin-1", "replace").decode("latin-1")
        if amount is None:
            doc.multi_cell(0, 6, normalized, fill=prominent)
        else:
            # A compact statement row, allowing long account names to wrap.
            text_width = doc.w - doc.l_margin - doc.r_margin - 43
            x, y = doc.get_x(), doc.get_y()
            doc.multi_cell(text_width, 6, normalized, fill=prominent)
            new_y = doc.get_y()
            doc.set_xy(x + text_width, y)
            doc.cell(43, 6, f"{Decimal(amount):,.2f}", align="R", fill=prominent)
            doc.set_xy(x, max(new_y, doc.get_y()))
    return bytes(doc.output())


@staff_member_required(login_url="/admin/login/")
def report_download(request, kind, format):
    if kind == "pl":
        form = ProfitLossDates(request.GET if request.GET else default_profit_loss_dates())
        report = profit_and_loss(**form.cleaned_data) if form.is_valid() else None
        dates = f"{form.cleaned_data['start']}_{form.cleaned_data['end']}" if report else ""
        name = "profit_loss"
    elif kind == "bs":
        form = BalanceSheetDate(request.GET if request.GET else default_balance_sheet_date())
        report = balance_sheet(form.cleaned_data["as_of"]) if form.is_valid() else None
        dates = str(form.cleaned_data["as_of"]) if report else ""
        name = "balance_sheet"
    else:
        return HttpResponseBadRequest("Unknown report.")
    if report is None:
        return HttpResponseBadRequest("Invalid report dates.")
    rows = report_rows(kind, report)
    if format == "xlsx":
        content = make_xlsx(rows)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        content = make_pdf(rows)
        content_type = "application/pdf"
    else:
        return HttpResponseBadRequest("Unknown export format.")
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{name}_{dates}.{format}"'
    response["Cache-Control"] = "no-store"
    return response
