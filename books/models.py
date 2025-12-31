from django.db import models

# Admin-only proxy model (no DB table). Shows in Admin under "Django Ledger".
class AdminReports(models.Model):
    class Meta:
        managed = False
        app_label = "django_ledger"   # groups it with Django Ledger in /admin
        verbose_name = "Reports"
        verbose_name_plural = "Reports"


