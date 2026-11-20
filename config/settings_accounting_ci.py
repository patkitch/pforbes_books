"""Isolated SQLite settings for accounting tests on the development branch.

Never use these settings for production data or deployed inventory/automation.
"""
SECRET_KEY = "accounting-test-only-not-for-deployment"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounting.apps.AccountingConfig",
    "accounting_contacts.apps.AccountingContactsConfig",
    "accounting_imports.apps.AccountingImportsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls_accounting_ci"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "DIRS": [],
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]
    },
}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
TIME_ZONE = "America/Chicago"
STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
