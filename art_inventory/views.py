from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from .forms import ActivityForm,ArtworkEditForm,ArtworkForm,PrintOptionForm
from .models import Artwork,InventoryActivity,Location,Original,PrintOption

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
    form=ActivityForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: activity=form.save(request.user)
        except (ValidationError,Original.DoesNotExist,PrintOption.DoesNotExist) as exc: form.add_error(None,exc)
        else:
            messages.success(request,"Inventory activity recorded.")
            art=activity.original.artwork if activity.original_id else activity.print_option.artwork
            return redirect("art_inventory:detail",pk=art.pk)
    return render(request,"art_inventory/form.html",{"form":form,"title":"Record inventory activity"})

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
        pdf=FPDF(); pdf.set_auto_page_break(auto=True,margin=14); pdf.add_page(); pdf.set_font("Helvetica","B",16); pdf.cell(0,10,"P. Forbes Art Inventory Report",ln=1)
        pdf.set_font("Helvetica","",9); pdf.cell(0,7,"Generated "+timezone.localdate().isoformat(),ln=1)
        def line(text):
            clean=str(text).encode("latin-1","replace").decode("latin-1")
            pdf.multi_cell(0,5,clean)
        pdf.set_font("Helvetica","B",12); pdf.cell(0,8,"Originals",ln=1); pdf.set_font("Helvetica","",9)
        for o in originals: line(f'{o.artwork.title} | {o.sku} | {o.get_status_display()} | {o.location or "No location"} | {o.get_canvas_profile_display()} | {o.price or ""}')
        pdf.ln(3); pdf.set_font("Helvetica","B",12); pdf.cell(0,8,"Print stock",ln=1); pdf.set_font("Helvetica","",9)
        for p in prints:
            stock="; ".join(f"{s.location}: {s.quantity}" for s in p.stock.all()) or "No stock"
            line(f"{p.artwork.title} | {p.sku} | {p.get_print_type_display()} | {stock} | {p.price or ''}")
        pdf.ln(3); pdf.set_font("Helvetica","B",12); pdf.cell(0,8,"Activity history",ln=1); pdf.set_font("Helvetica","",9)
        for a in activities:
            item=a.original.artwork.title if a.original_id else a.print_option.artwork.title
            line(f"{a.activity_date} | {a.get_kind_display()} | {item} | qty {a.quantity} | from {a.from_location or '-'} | to {a.to_location or '-'} | refund: {("yes" if a.refund_issued else "no") if a.kind=="original_return" else "-"} | {a.note}")
        out=pdf.output(dest="S")
        response=HttpResponse(bytes(out),content_type="application/pdf")
        response["Content-Disposition"]='attachment; filename="pforbes-inventory-report.pdf"'
        return response
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
