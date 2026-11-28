"""Staff-only two-step approval with signed exact preview and atomic posting."""
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import render
from accounting.models import Account
from accounting.import_preview import eligible_import_accounts
from .models import ImportRow,WooOrderImport,StripePaymentImport,StripeAdjustment,WooPayoutMatch,StripePayoutMatch,StripeGroupMatch
from .posting import build,existing,row_posted,write,EXPENSE,INCOME
from .stripe_imports import classify
from .woo_payouts import eligible_order

class MappingForm(forms.Form):
    stripe_clearing=forms.ModelChoiceField(queryset=Account.objects.none(),required=False)
    woo_clearing=forms.ModelChoiceField(queryset=Account.objects.none(),required=False,label="WooPayments clearing")
    website_revenue=forms.ModelChoiceField(queryset=Account.objects.none(),required=False)
    shipping_income=forms.ModelChoiceField(queryset=Account.objects.none(),required=False)
    tax_payable=forms.ModelChoiceField(queryset=Account.objects.none(),required=False)
    processor_fee=forms.ModelChoiceField(queryset=Account.objects.none(),required=False)
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        active=Account.objects.filter(is_active=True)
        assets=active.filter(account_type="asset").exclude(pk__in=eligible_import_accounts().values("pk"))
        for k in ("stripe_clearing","woo_clearing"): self.fields[k].queryset=assets
        for k in ("website_revenue","shipping_income"): self.fields[k].queryset=active.filter(account_type__in=INCOME)
        self.fields["tax_payable"].queryset=active.filter(account_type="liability").exclude(pk__in=eligible_import_accounts().values("pk"))
        self.fields["processor_fee"].queryset=active.filter(account_type__in=EXPENSE)
        if not self.is_bound:
            self.initial.setdefault("website_revenue",active.filter(number="4014").values_list("pk",flat=True).first())

def candidates():
    items=[]
    for r in ImportRow.objects.filter(status=ImportRow.REVIEWED):
        if not row_posted(r.pk): items.append(("bank:"+str(r.pk),r.transaction_date,r.description,r.amount))
    for o in WooOrderImport.objects.filter(review_status=WooOrderImport.RECEIPTED):
        if eligible_order(o) and not existing("woo:"+str(o.pk)): items.append(("woo:"+str(o.pk),o.order_date,"Woo #"+str(o.source_order_id)+" "+o.customer_name,o.total))
    for p in StripePaymentImport.objects.all():
        if p.review_data.get("state")=="reviewed" and classify(p)[0]=="Possible direct sale — review required" and not existing("stripe:"+str(p.pk)): items.append(("stripe:"+str(p.pk),p.created_utc.date(),p.customer_name or p.charge_id,p.gross))
    for a in StripeAdjustment.objects.filter(voided_at__isnull=True):
        if not existing("adjustment:"+str(a.pk)): items.append(("adjustment:"+str(a.pk),a.day,a.get_kind_display()+" "+a.balance_id,a.net))
    ids=set()
    for model in (WooPayoutMatch,StripePayoutMatch,StripeGroupMatch): ids.update(model.objects.filter(undone_at__isnull=True).values_list("bank_row_id",flat=True))
    for r in ImportRow.objects.filter(pk__in=ids,status=ImportRow.PENDING):
        if not row_posted(r.pk): items.append(("payout:"+str(r.pk),r.transaction_date,r.description,r.amount))
    return sorted(items,key=lambda x:(x[1],x[0]))

def serialize(plan):
    return dict(key=plan.key,day=plan.day.isoformat(),label=plan.label,memo=plan.memo,vendor=plan.vendor.pk if plan.vendor else None,customer=plan.customer.pk if plan.customer else None,receipts=[r.pk for r in plan.receipts],rows=[r.pk for r in plan.rows],lines=[[a.pk,str(d),str(c)] for a,d,c in plan.lines])

@staff_member_required(login_url="/admin/login/")
def center(request):
    form=MappingForm(request.POST if request.method=="POST" and request.POST.get("action")=="preview" else None,initial=request.session.get("posting_mapping",{}))
    error=None
    plans=[]
    token=""
    result=[]
    if request.method=="POST":
        try:
            if request.POST.get("action")=="preview" and form.is_valid():
                cfg={k:v.pk if v else None for k,v in form.cleaned_data.items()}
                keys=list(dict.fromkeys(request.POST.getlist("selected")))
                if not keys or len(keys)>100 or not set(keys)<= {i[0] for i in candidates()}: raise ValidationError("Select 1 to 100 available transactions.")
                # Preview dependent entries in a rolled-back savepoint. Nothing persists.
                with transaction.atomic():
                    for key in sorted(keys,key=lambda k:{"woo":0,"stripe":0,"bank":1,"adjustment":2,"payout":3}[k.split(":")[0]]):
                        plan=build(key,cfg,True)
                        plans.append(plan)
                        write(plan,request.user)
                    transaction.set_rollback(True)
                token=signing.dumps(dict(user=request.user.pk,cfg=cfg,keys=keys,plans=[serialize(p) for p in plans]),salt="import-posting-v1")
                request.session["posting_mapping"]=cfg
            elif request.POST.get("action")=="post":
                if request.POST.get("confirm")!="yes": raise ValidationError("Explicit approval required.")
                data=signing.loads(request.POST.get("token",""),salt="import-posting-v1",max_age=1800)
                if data["user"]!=request.user.pk: raise ValidationError("Preview belongs to another user.")
                with transaction.atomic():
                    for key,expected in zip(sorted(data["keys"],key=lambda k:{"woo":0,"stripe":0,"bank":1,"adjustment":2,"payout":3}[k.split(":")[0]]),data["plans"]):
                        plan=build(key,data["cfg"],True)
                        if serialize(plan)!=expected: raise ValidationError("Source or mapping changed. Preview again.")
                        result.append(write(plan,request.user))
        except (ValidationError,IntegrityError,signing.BadSignature) as exc:
            error="; ".join(exc.messages) if isinstance(exc,ValidationError) else "Preview expired, duplicate source, or concurrent update. Nothing posted."
            plans=[];result=[];token=""
    return render(request,"accounting_imports/posting_center.html",dict(form=form,items=candidates(),error=error,plans=plans,token=token,result=result))
