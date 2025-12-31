from django.apps import AppConfig
import os

class HelpersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpers"
    verbose_name = "Helpers"

    # Tell Django "THIS is the canonical location of the helpers app."
    path = os.path.dirname(os.path.abspath(__file__))