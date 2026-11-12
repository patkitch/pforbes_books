from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from .forms import ActivityForm,ArtworkEditForm,ArtworkForm,PrintOptionForm
from .models import Artwork,InventoryActivity,Location,Original,PrintOption


class InventoryReportPDF(FPDF):
    def header(self):
        self.set_fill_color(23, 49, 73)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.cell(self.epw, 12, "P. Forbes Art Inventory Report", border=0, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def footer(self):
        self.set_draw_color(220, 227, 235)
        self.line(self.l_margin, self.h - 14, self.w - self.r_margin, self.h - 14)
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100, 116, 138)
        self.cell(self.epw, 6, f"Page {self.page_no()}/{{nb}}", align="R")

def _pdf_text(pdf, value, *, bold=False, size=9, color=(24, 36, 56), fill=False):
    text = str(value or "")
    text = text.replace("×", "x").replace("—", "-").replace("–", "-").replace("’", "'")
    text = text.encode("latin-1", "replace").decode("latin-1")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.set_text_color(*color)
    if fill:
        pdf.set_fill_color(242, 245, 249)
    pdf.multi_cell(
        w=pdf.epw, h=5, text=text, border=0, fill=fill,
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, wrapmode="CHAR",
    )

def _pdf_rule(pdf):
    y = pdf.get_y() + 1
    pdf.set_draw_color(220, 227, 235)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_y(y + 3)

def _pdf_section(pdf, title):
    pdf.ln(3)
    pdf.set_fill_color(23, 49, 73)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_x(pdf.l_margin)
    pdf.cell(pdf.epw, 8, title, border=0, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

def _inventory_pdf_response(originals, prints, activities):
    pdf = InventoryReportPDF(format="Letter")
    pdf.set_margins(15, 12, 15)
    pdf.set_auto_page_break(auto=True, margin=17)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 138)
    _pdf_text(pdf, "Generated " + timezone.localdate().isoformat(), size=8, color=(100, 116, 138))
    _pdf_rule(pdf)

    _pdf_section(pdf, "ORIGINALS")
    if not originals.exists():
        _pdf_text(pdf, "No original artworks recorded.", color=(100, 116, 138))
    for original in originals:
        art = original.artwork
        price = f"${original.price:,.2f}" if original.price is not None else "Not set"
        _pdf_text(pdf, art.title, bold=True, size=10, fill=True)
        _pdf_text(pdf, f"SKU: {original.sku}  |  Status: {original.get_status_display()}  |  Location: {original.location or 'None'}  |  Price: {price}")
        details = f"Medium: {art.medium or 'Not recorded'}  |  Style: {art.style or 'Not recorded'}  |  Surface: {art.support or 'Not recorded'}"
        _pdf_text(pdf, details)
        dimensions = f"Canvas: {original.get_canvas_profile_display() or 'Not recorded'}  |  {'Framed' if original.framed else 'Unframed'}"
        if original.outside_width_inches or original.outside_height_inches:
            dimensions += f"  |  Outside size: {original.outside_width_inches or '?'} x {original.outside_height_inches or '?'} in"
        _pdf_text(pdf, dimensions)
        _pdf_rule(pdf)

    _pdf_section(pdf, "PRINT STOCK")
    if not prints.exists():
        _pdf_text(pdf, "No print sizes recorded.", color=(100, 116, 138))
    for option in prints:
        price = f"${option.price:,.2f}" if option.price is not None else "Not set"
        _pdf_text(pdf, f"{option.artwork.title} - {option.get_print_type_display()}", bold=True, size=10, fill=True)
        _pdf_text(pdf, f"SKU: {option.sku}  |  Selling price: {price}")
        stock_rows = list(option.stock.select_related("location").all())
        stock = "  |  ".join(f"{row.location}: {row.quantity} on hand" for row in stock_rows) or "No stock counted"
        _pdf_text(pdf, "On hand: " + stock)
        _pdf_rule(pdf)

    _pdf_section(pdf, "ACTIVITY HISTORY")
    if not activities.exists():
        _pdf_text(pdf, "No inventory activity recorded.", color=(100, 116, 138))
    for activity in activities:
        item = activity.original.artwork.title if activity.original_id else activity.print_option.artwork.title
        _pdf_text(pdf, f"{activity.activity_date.isoformat()}  |  {activity.get_kind_display()}  |  {item}", bold=True, size=9, fill=True)
        details = f"Quantity: {activity.quantity}  |  From: {activity.from_location or '-'}  |  To: {activity.to_location or '-'}"
        if activity.kind == "original_return":
            details += "  |  Refund: " + ("Issued" if activity.refund_issued else "Not issued")
        _pdf_text(pdf, details)
        if activity.source or activity.reference:
            _pdf_text(pdf, f"Source: {activity.source or '-'}  |  Reference: {activity.reference or '-'}", size=8, color=(100, 116, 138))
        if activity.note:
            _pdf_text(pdf, "Reason / notes: " + activity.note, size=8, color=(100, 116, 138))
        _pdf_rule(pdf)

    response = HttpResponse(bytes(pdf.output(dest="S")), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="pforbes-inventory-report.pdf"'
    return response

@login_required
def home(request):
    q=request.GET.get("q","").strip(); loc=request.GET.get("location","")
    items=Artwork.objects.select_related("original__location").prefetch_related("print_options__stock__location")
    if q: items=items.filter(Q(title__icontains=q)|Q(original__sku__icontains=q)|Q(print_options__sku__icontains=q)).distinct()
    if loc.isdigit(): items=items.filter(Q(original__location_id=loc)|Q(print_options__stock__location_id=loc,print_options__stock__quantity__gt=0)).distinct()
    return render(request,"art_inventory/home.html",{"items":items,"q":q,"loc":loc,"locations":Location.objects.filter(is_active=True)})

@login_required
def artwork_add(request):
    form=ArtworkForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        art=form.save(); messages.success(request,"Artwork and original inventory record added.")
        return redirect("art_inventory:detail",pk=art.pk)
    return render(request,"art_inventory/form.html",{"form":form,"title":"Add original artwork"})

@login_required
def artwork_edit(request,pk):
    art=get_object_or_404(Artwork.objects.select_related("original"),pk=pk)
    form=ArtworkEditForm(request.POST or None,artwork=art,original=art.original)
    if request.method=="POST" and form.is_valid():
        form.save(request.user); messages.success(request,"Original details updated; the title and edit history were preserved.")
        return redirect("art_inventory:detail",pk=art.pk)
    return render(request,"art_inventory/form.html",{"form":form,"title":"Edit original details"})

@login_required
def detail(request,pk):
    art=get_object_or_404(Artwork.objects.select_related("original__location").prefetch_related("print_options__stock__location"),pk=pk)
    original=getattr(art,"original",None)
    history_query=Q(print_option__artwork=art)
    if original: history_query |= Q(original=original)
    history=InventoryActivity.objects.filter(history_query).select_related("from_location","to_location","original__artwork","print_option__artwork")[:40]
    return render(request,"art_inventory/detail.html",{"art":art,"original":original,"history":history})

@login_required
def print_add(request):
    form=PrintOptionForm(request.POST or None,initial={"artwork":request.GET.get("artwork") or None})
    if request.method=="POST" and form.is_valid():
        try: option=form.save(request.user)
        except (ValidationError,Original.DoesNotExist,PrintOption.DoesNotExist) as exc: form.add_error(None,exc)
        else:
            messages.success(request,"Print size added to local inventory.")
            return redirect("art_inventory:detail",pk=option.artwork_id)
    return render(request,"art_inventory/form.html",{"form":form,"title":"Add print inventory"})

@login_required
def activity_add(request):
    form=ActivityForm(request.POST or None,initial={"item_type":request.GET.get("item_type") or None,"print_option":request.GET.get("print_option") or None,"kind":request.GET.get("kind") or None})
    if request.method=="POST" and form.is_valid():
        try: activity=form.save(request.user)
        except (ValidationError,Original.DoesNotExist,PrintOption.DoesNotExist) as exc: form.add_error(None,exc)
        else:
            messages.success(request,"Inventory activity recorded.")
            art=activity.original.artwork if activity.original_id else activity.print_option.artwork
            return redirect("art_inventory:detail",pk=art.pk)
    return render(request,"art_inventory/form.html",{"form":form,"title":"Record a sale or stock change"})

@login_required
def artwork_delete(request,pk):
    art=get_object_or_404(Artwork.objects.select_related("original").prefetch_related("print_options__stock"),pk=pk)
    original=getattr(art,"original",None)
    history_count=InventoryActivity.objects.filter(Q(original=original) if original else Q(pk__in=[])).count()
    if art.print_options.exists(): history_count += InventoryActivity.objects.filter(print_option__artwork=art).count()
    if request.method=="POST" and request.POST.get("confirm_title","").strip()==art.title:
        # Explicitly confirmed deletion removes this artwork's stock and its linked activity history as one unit.
        InventoryActivity.objects.filter(Q(original=original) if original else Q(pk__in=[])).delete()
        InventoryActivity.objects.filter(print_option__artwork=art).delete()
        art.delete()
        messages.success(request,"Artwork, print stock, and its activity history were deleted.")
        return redirect("art_inventory:home")
    return render(request,"art_inventory/confirm_delete.html",{"art":art,"history_count":history_count,"delete_url":request.path,"kind":"artwork"})

@login_required
def print_delete(request,pk):
    option=get_object_or_404(PrintOption.objects.select_related("artwork"),pk=pk)
    history_count=InventoryActivity.objects.filter(print_option=option).count()
    if request.method=="POST" and request.POST.get("confirm_title","").strip()==option.sku:
        InventoryActivity.objects.filter(print_option=option).delete()
        art_id=option.artwork_id
        option.delete()
        messages.success(request,"Print option, stock, and its activity history were deleted.")
        return redirect("art_inventory:detail",pk=art_id)
    return render(request,"art_inventory/confirm_delete.html",{"art":option.artwork,"print_option":option,"history_count":history_count,"delete_url":request.path,"kind":"print"})

@login_required
def inventory_report(request):
    originals=Original.objects.select_related("artwork","location").order_by("artwork__title")
    prints=PrintOption.objects.select_related("artwork").prefetch_related("stock__location").order_by("artwork__title","print_type")
    activities=InventoryActivity.objects.select_related("original__artwork","print_option__artwork","from_location","to_location","created_by").order_by("activity_date","created_at")
    if request.GET.get("format")=="pdf":
        return _inventory_pdf_response(originals,prints,activities)
    wb=Workbook(); ws=wb.active; ws.title="Originals"
    ws.append(["Title","SKU","Status","Location","Price","Canvas profile","Framed","Outside size","Painting surface"])
    for o in originals: ws.append([o.artwork.title,o.sku,o.get_status_display(),o.location.name if o.location else "",float(o.price) if o.price is not None else "",o.get_canvas_profile_display(), "Yes" if o.framed else "No",f"{o.outside_width_inches or ''} × {o.outside_height_inches or ''}",o.artwork.support])
    ws2=wb.create_sheet("Print stock"); ws2.append(["Title","Print type","SKU","Location","Quantity","Selling price"])
    for p in prints:
        rows=list(p.stock.all())
        if rows:
            for s in rows: ws2.append([p.artwork.title,p.get_print_type_display(),p.sku,s.location.name,s.quantity,float(p.price) if p.price is not None else ""])
        else: ws2.append([p.artwork.title,p.get_print_type_display(),p.sku,"",0,float(p.price) if p.price is not None else ""])
    ws3=wb.create_sheet("Activity"); ws3.append(["Date","Activity","Item","SKU","Quantity","From","To","Refund issued","Source","Reference","Note"])
    for a in activities:
        item=a.original.artwork if a.original_id else a.print_option.artwork
        sku=a.original.sku if a.original_id else a.print_option.sku
        ws3.append([a.activity_date.isoformat(),a.get_kind_display(),item.title,sku,a.quantity,a.from_location.name if a.from_location else "",a.to_location.name if a.to_location else "", "Yes" if a.refund_issued else "No",a.source,a.reference,a.note])
    for sheet in wb.worksheets:
        sheet.freeze_panes="A2"; sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:
            cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="17324D")
        for col in sheet.columns:
            letter=col[0].column_letter
            width=min(max(max((len(str(c.value or "")) for c in col),default=8)+2,12),45)
            sheet.column_dimensions[letter].width=width
    data=BytesIO(); wb.save(data)
    response=HttpResponse(data.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"]='attachment; filename="pforbes-inventory-report.xlsx"'
    return response
