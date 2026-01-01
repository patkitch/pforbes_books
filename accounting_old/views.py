from django.shortcuts import render

# Create your views here.
# accounting/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ApplyPaymentForm
from .models import Invoice, Customer  # adjust path
from .services.payments import apply_payment
from .forms import ApplyBillPaymentForm
from django_ledger.models import BillModel, InvoiceModel


@login_required
@permission_required("accounting.add_payment", raise_exception=True)
@permission_required("accounting.add_billpayment", raise_exception=True)

def apply_bill_payment_view(request):
    if request.method == "POST":
        form = ApplyBillPaymentForm(request.POST)
        if form.is_valid():
            bill = form.cleaned_data["bill"]
            vendor = form.cleaned_data["vendor"]
            payment_date = form.cleaned_data["payment_date"]
            payment_amount = form.cleaned_data["payment_amount"]
            discount_amount = form.cleaned_data["discount_amount"]
            method = form.cleaned_data["method"]
            reference = form.cleaned_data["reference"]
            try:
                from .services.bill_payments import apply_bill_payment
                bp, updated_bill = apply_bill_payment(
                    bill=bill, vendor=vendor,
                    payment_amount=payment_amount, discount_amount=discount_amount,
                    payment_date=payment_date, method=method, reference=reference,
                    user=request.user,
                )
            except Exception as e:
                messages.error(request, f"Could not apply bill payment: {e}")
            else:
                messages.success(
                    request,
                    f"Bill payment of {bp.amount:,.2f}"
                    f"{' (discount ' + str(bp.discount_taken) + ')' if bp.discount_taken else ''} "
                    f"applied to Bill {getattr(updated_bill, 'number', updated_bill.pk)}."
                )
                return redirect(request.path)
    else:
        initial = {}
        bill_id = request.GET.get("bill")
        if bill_id:
            bill = get_object_or_404(BillModel, pk=bill_id)
            initial["bill"] = bill
            if hasattr(bill, "vendor"):
                initial["vendor"] = bill.vendor
        form = ApplyBillPaymentForm(initial=initial)

    return render(request, "accounting/apply_bill_payment.html", {"form": form})

def apply_payment_view(request):
    if request.method == "POST":
        form = ApplyPaymentForm(request.POST)
        if form.is_valid():
            invoice = form.cleaned_data["invoice"]
            customer = form.cleaned_data["customer"]
            payment_date = form.cleaned_data["payment_date"]
            payment_amount = form.cleaned_data["payment_amount"]
            discount_amount = form.cleaned_data["discount_amount"]
            method = form.cleaned_data["method"]
            reference = form.cleaned_data["reference"]

            try:
                from .services.payments import apply_payment
                payment, updated_invoice = apply_payment(
                    invoice=invoice,
                    customer=customer,
                    payment_amount=payment_amount,
                    discount_amount=discount_amount,
                    payment_date=payment_date,
                    method=method,
                    reference=reference,
                    user=request.user,
                )
            except Exception as e:
                messages.error(request, f"Could not apply payment: {e}")
            else:
                messages.success(
                    request,
                    f"Payment of {payment.amount:,.2f}"
                    f"{' (incl. discount ' + str(payment.discount_taken) + ')' if payment.discount_taken else ''} "
                    f"applied to Invoice {getattr(updated_invoice, 'number', updated_invoice.pk)}."
                )
                # Adjust detail URL if you have one; otherwise, redirect back to the form.
                return redirect(request.path)
    else:
        initial = {}
        inv_id = request.GET.get("invoice")
        if inv_id:
            invoice = get_object_or_404(InvoiceModel, pk=inv_id)
            initial["invoice"] = invoice
            # If InvoiceModel has `.customer`, this will prefill:
            if hasattr(invoice, "customer"):
                initial["customer"] = invoice.customer
        form = ApplyPaymentForm(initial=initial)

    return render(request, "accounting/apply_payment.html", {"form": form})
