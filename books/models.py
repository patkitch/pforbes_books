from django.db import models

# Admin-only proxy model (no DB table). Shows in Admin under "Django Ledger".
class AdminReports(models.Model):
    class Meta:
        managed = False
        app_label = "django_ledger"   # groups it with Django Ledger in /admin
        verbose_name = "Reports"
        verbose_name_plural = "Reports"


# books/models.py
from django.db import models
from django_ledger.models import BillModel, AccountModel

class BillExtras(models.Model):
    bill = models.OneToOneField(BillModel, on_delete=models.CASCADE, related_name="extras")

    # Default posting targets (choose what you want to expose)
    default_expense_acct = models.ForeignKey(
        AccountModel, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bill_default_expense_accounts",
        help_text="Expense account to use for lines without a specific account."
    )
    cash_account_override = models.ForeignKey(
        AccountModel, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bill_cash_accounts",
        help_text="Override cash/bank account when marking bill paid."
    )

    # Discounts at the bill header level
    DISCOUNT_METHODS = [
        ("PCT", "Percent"),
        ("AMT", "Fixed Amount"),
    ]
    discount_method = models.CharField(max_length=3, choices=DISCOUNT_METHODS, default="AMT")
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_account = models.ForeignKey(
        AccountModel, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bill_discount_accounts",
        help_text="Contra-expense or purchase discount account."
    )

    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Extras for Bill {self.bill.uuid}"
