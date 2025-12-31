# accounting/models.py  (minimal Payment model to support the flow)
from django.db import models
from django.conf import settings

class Payment(models.Model):
    # Point to Django-Ledger models
    invoice = models.ForeignKey(
        "django_ledger.InvoiceModel",
        on_delete=models.PROTECT,
        related_name="payments"  # this adds a reverse accessor on the ledger model
    )
    customer = models.ForeignKey(
        "django_ledger.CustomerModel",
        on_delete=models.PROTECT,
        related_name="payments"
    )
class BillPayment(models.Model):
    bill = models.ForeignKey(
        "django_ledger.BillModel",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    vendor = models.ForeignKey(
        "django_ledger.VendorModel",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_taken = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=16)
    reference = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Payment {self.pk} for Invoice {getattr(self.invoice, 'number', self.invoice_id)}"
