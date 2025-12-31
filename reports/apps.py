from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
import os

class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = _("Reports")
    path = os.path.dirname(os.path.abspath(__file__))  # 👈 tell Django where this app lives

