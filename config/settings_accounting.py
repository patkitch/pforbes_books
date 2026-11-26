"""Local accounting development only. Never use for production deployment."""
from .settings import *
from django.core.exceptions import ImproperlyConfigured

db = DATABASES["default"]
if (
    db.get("ENGINE") != "django.db.backends.postgresql"
    or db.get("NAME") != "pforbes_books_accounting_test"
    or db.get("HOST") not in ("127.0.0.1", "localhost", "::1")
    or str(db.get("PORT") or "5432") != "5432"
):
    raise ImproperlyConfigured("Accounting development requires the local pforbes_books_accounting_test PostgreSQL database.")

for app in ("accounting.apps.AccountingConfig",
            "accounting_contacts.apps.AccountingContactsConfig",
            "accounting_imports.apps.AccountingImportsConfig",
            "accounting_profile.apps.AccountingProfileConfig"):
    if not any(existing.split(".")[0] == app.split(".")[0] for existing in INSTALLED_APPS):
        INSTALLED_APPS = [*INSTALLED_APPS, app]

ROOT_URLCONF = "config.urls_accounting"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
