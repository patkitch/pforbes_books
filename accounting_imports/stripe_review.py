"""Complete missing direct Stripe sale details without creating a receipt or journal."""
from decimal import Decimal
from zoneinfo import ZoneInfo
from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounting.models import Account
from accounting_contacts.models import Customer
from .models import StripePaymentImport
from .stripe_imports import classify

DIRECT = "Possible direct sale — review required"
NONNEG = dict(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))


class SaleForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label="Existing customer (optional)")
    customer_name = forms.CharField(max_length=200)
    customer_email = forms.EmailField(max_length=254, required=False)
    billing_address1 = forms.CharField(max_length=200, required=False, label="Billing street address")
    billing_city = forms.CharField(max_length=100, required=False, label="City")
    billing_state = forms.CharField(max_length=100, required=False, label="State")
    billing_postal_code = forms.CharField(max_length=24, required=False, label="Postal code")
    billing_country = forms.CharField(max_length=80, required=False, label="Country")
    artwork = forms.CharField(max_length=200, label="Artwork / item")
    item_type = forms.ChoiceField(choices=[("print","Fine art print"),("original","Original artwork"),("other","Other")])
    size = forms.CharField(max_length=80, required=False)
    quantity = forms.IntegerField(min_value=1, max_value=10000, initial=1)
    unit_price = forms.DecimalField(**NONNEG)
    shipping = forms.DecimalField(**NONNEG, label="Shipping charged")
    tax = forms.DecimalField(**NONNEG, label="Sales tax collected")
    revenue = forms.ModelChoiceField(queryset=Account.objects.none(), label="Revenue account")
    shipping_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False, label="Shipping income account")
    tax_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False, label="Sales tax payable account")
    jurisdiction = forms.CharField(max_length=160, required=False, label="Tax jurisdiction (if tax collected)")
    memo = forms.CharField(max_length=500, required=False, widget=forms.Textarea(attrs={"rows":3}))
    confirm = forms.BooleanField(label="I verified this is a direct business sale, not a WooCommerce sale or personal test payment.")

    def __init__(self, *args, payment, **kwargs):
        super().__init__(*args, **kwargs)
        self.payment = payment
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        income = Account.objects.filter(is_active=True, account_type="income")
        self.fields["revenue"].queryset = income
        self.fields["shipping_account"].queryset = income
        self.fields["tax_account"].queryset = Account.objects.filter(is_active=True, account_type="liability")

    def clean(self):
        data = super().clean()
        customer = data.get("customer")
        email = data.get("customer_email","")
        original = self.payment.customer_email.strip()
        if original and email.casefold() != original.casefold():
            self.add_error("customer_email","Keep the imported payment email. Resolve discrepancies before reviewing.")
        matches = Customer.objects.filter(email__iexact=email) if email else Customer.objects.none()
        if matches.count()>1 or matches.filter(is_active=False).exists():
            self.add_error("customer","Resolve ambiguous or inactive email matches in the customer directory first.")
        if customer and (not email or customer.email.casefold()!=email.casefold()):
            self.add_error("customer","Select a customer with the same verified email.")
        if not customer and matches.exists():
            self.add_error("customer","Select the existing customer with this email.")
        qty, price, shipping, tax = (data.get(k) for k in ("quantity","unit_price","shipping","tax"))
        if None not in (qty,price,shipping,tax):
            if qty*price+shipping+tax != self.payment.gross:
                self.add_error("unit_price","Quantity × unit price + shipping + tax must equal the imported gross payment exactly.")
            if shipping and not data.get("shipping_account"):
                self.add_error("shipping_account","Select the shipping income account.")
            if tax and (not data.get("tax_account") or not data.get("jurisdiction")):
                self.add_error("tax","Select the tax payable account and jurisdiction.")
        return data


def record_review(payment, actor, data, action):
    history = list(payment.review_history)
    history.append({"action":action,"at":timezone.now().isoformat(),"by":actor.pk,"previous":payment.review_data})
    payment.review_history = history
    payment.review_data = data
    payment.save(update_fields=["review_history","review_data"])


@staff_member_required(login_url="/admin/login/")
@transaction.atomic
def review(request, pk):
    payment = get_object_or_404(StripePaymentImport.objects.select_for_update(), pk=pk)
    label, order = classify(payment)
    eligible = label == DIRECT
    current = payment.review_data
    initial = {"customer_name":payment.customer_name,"customer_email":payment.customer_email,"quantity":1}
    if current.get("state")=="reviewed":
        initial.update(current)
    elif payment.customer_email:
        matches = list(Customer.objects.filter(email__iexact=payment.customer_email)[:2])
        if len(matches)==1 and matches[0].is_active:
            c=matches[0]
            initial.update({"customer":c.pk,"customer_name":c.name,**{k:getattr(c,k) for k in ("billing_address1","billing_city","billing_state","billing_postal_code","billing_country")}})
    action = request.POST.get("action") if request.method=="POST" else ""
    form = SaleForm(request.POST if action=="save" else None, payment=payment, initial=initial)
    if request.method=="POST":
        if action=="restore" and current.get("state")=="excluded" and request.POST.get("confirm")=="yes":
            record_review(payment,request.user,{},"restore")
            return redirect("accounting:stripe_review",pk=pk)
        if not eligible or current.get("state")=="excluded":
            return HttpResponseBadRequest("Payment is not eligible for direct sale review.")
        if action=="exclude":
            reason=request.POST.get("reason","").strip()
            if request.POST.get("confirm")!="yes" or not reason or len(reason)>500:
                return HttpResponseBadRequest("Confirm personal/test exclusion and provide a reason.")
            record_review(payment,request.user,{"state":"excluded","reason":reason},"exclude")
            return redirect("accounting:stripe_review",pk=pk)
        if action!="save":
            return HttpResponseBadRequest("Invalid review action.")
        if form.is_valid():
            data={}
            for k,v in form.cleaned_data.items():
                if k=="confirm":
                    continue
                data[k]=str(v) if isinstance(v,Decimal) else v.pk if isinstance(v,(Account,Customer)) else v
            data.update(state="reviewed", sale_date=payment.created_utc.astimezone(ZoneInfo("America/Chicago")).date().isoformat())
            record_review(payment,request.user,data,"save")
            return redirect("accounting:stripe_review",pk=pk)
    return render(request,"accounting_imports/stripe_review.html",{"payment":payment,"form":form,"eligible":eligible,
        "label":label,"review":current,"net":payment.gross-payment.fee,"history":payment.review_history})
