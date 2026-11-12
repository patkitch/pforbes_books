from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
from .forms import ActivityForm,ArtworkForm,PrintOptionForm
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
def detail(request,pk):
    art=get_object_or_404(Artwork.objects.select_related("original__location").prefetch_related("print_options__stock__location"),pk=pk)
    original=getattr(art,"original",None)
    history=InventoryActivity.objects.filter(Q(original=original)|Q(print_option__artwork=art)).select_related("from_location","to_location","original__artwork","print_option__artwork")[:40]
    return render(request,"art_inventory/detail.html",{"art":art,"history":history})

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
