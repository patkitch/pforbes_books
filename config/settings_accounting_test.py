"""Isolated automated accounting tests; never use for interactive bookkeeping."""
from .settings import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
for app in ("accounting.apps.AccountingConfig",
            "accounting_contacts.apps.AccountingContactsConfig",
            "accounting_imports.apps.AccountingImportsConfig",
            "accounting_profile.apps.AccountingProfileConfig"):
    if not any(existing.split(".")[0] == app.split(".")[0] for existing in INSTALLED_APPS):
        INSTALLED_APPS = [*INSTALLED_APPS, app]
ROOT_URLCONF = "config.urls_accounting"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
