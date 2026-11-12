from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import InventoryActivity,Location,Original,PrintStock,PrintOption

@transaction.atomic
def record_activity(*,kind,quantity,activity_date=None,original_id=None,print_option_id=None,from_location_id=None,to_location_id=None,source="",reference="",note="",refund_issued=False,user=None):
    try: qty=int(quantity)
    except (TypeError,ValueError): raise ValidationError("Quantity must be a whole number.")
    if qty<1: raise ValidationError("Quantity must be at least 1.")
    original=Original.objects.select_for_update().select_related("artwork").get(pk=original_id) if original_id else None
    option=PrintOption.objects.select_for_update().get(pk=print_option_id) if print_option_id else None
    if bool(original)==bool(option): raise ValidationError("Choose exactly one inventory item.")
    locs={x.pk:x for x in Location.objects.filter(pk__in=[x for x in (from_location_id,to_location_id) if x])}
    if (from_location_id and from_location_id not in locs) or (to_location_id and to_location_id not in locs): raise ValidationError("Choose an existing location.")
    src,dst=locs.get(from_location_id),locs.get(to_location_id)
    if original:
        if qty!=1: raise ValidationError("An original has a quantity of one.")
        if kind not in ("transfer","original_sale","original_return","gift"): raise ValidationError("Choose an original activity.")
        if kind=="original_return":
            if original.status!="sold": raise ValidationError("Only an original marked sold can be returned.")
            if not dst: raise ValidationError("Choose the location receiving the returned original.")
            original.status="available"
            original.location=dst
        else:
            if original.status in ("sold","gifted"): raise ValidationError("This original is already sold or gifted.")
            if kind=="transfer":
                if not src or not dst or src==dst: raise ValidationError("Transfer needs two different locations.")
                if original.location_id!=src.pk: raise ValidationError("Original is not at the selected starting location.")
                original.location=dst
            else:
                if src and original.location_id!=src.pk: raise ValidationError("Original is not at the selected location.")
                original.status="sold" if kind=="original_sale" else "gifted"
                original.location=None
        original.save(update_fields=["location","status"])
    else:
        if refund_issued: raise ValidationError("Refund tracking applies only to an original return.")
        if kind not in ("purchase","return","transfer","local_sale","adjust_add","adjust_remove"): raise ValidationError("Choose a print activity.")
        if kind=="transfer":
            if not src or not dst or src==dst: raise ValidationError("Transfer needs two different locations.")
            _stock(option,src,-qty); _stock(option,dst,qty)
        elif kind in ("purchase","return","adjust_add"):
            if not dst: raise ValidationError("Choose the location receiving stock.")
            _stock(option,dst,qty)
        else:
            if not src: raise ValidationError("Choose the location losing stock.")
            _stock(option,src,-qty)
    return InventoryActivity.objects.create(kind=kind,quantity=qty,activity_date=activity_date or timezone.localdate(),original=original,print_option=option,from_location=src,to_location=dst,source=source,reference=reference,note=note,refund_issued=refund_issued,created_by=user if getattr(user,"is_authenticated",False) else None)

def _stock(option,location,delta):
    row,_=PrintStock.objects.get_or_create(print_option=option,location=location)
    row=PrintStock.objects.select_for_update().get(pk=row.pk)
    if row.quantity+delta<0: raise ValidationError(f"Not enough stock at {location}; recorded quantity is {row.quantity}.")
    row.quantity+=delta
    row.save(update_fields=["quantity"])
