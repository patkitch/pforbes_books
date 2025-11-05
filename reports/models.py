# reports/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _

class InventoryReconciliationReport(models.Model):
    """
    Virtual admin handle for the Inventory Reconciliation report.

    We mark this as unmanaged so Django will NOT try to create a table.
    We'll use ModelAdmin with custom views/buttons to download CSV, etc.
    """
    class Meta:
        managed = False  # no DB table
        verbose_name = _("Inventory Reconciliation")
        verbose_name_plural = _("Inventory Reconciliation")


class _ReportBase(models.Model):
    class Meta:
        abstract = True
        managed = False
        app_label = "reports"

class ITxSnapshotReport(_ReportBase):
    class Meta(_ReportBase.Meta):
        verbose_name = "ITx On-Hand Snapshot"
        verbose_name_plural = "ITx On-Hand Snapshot"

class ITxTxDetailReport(_ReportBase):
    class Meta(_ReportBase.Meta):
        verbose_name = "ITx Transaction Detail"
        verbose_name_plural = "ITx Transaction Detail"
