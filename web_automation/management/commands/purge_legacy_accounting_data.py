from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder


LEGACY_TABLE_PREFIXES = (
    "django_ledger_",
    "accounting_",
    "accounting_old_",
    "books_",
    "forbes_lawn_",
    "helpers_",
    "inventorystock_",
    "jobber_sync_",
    "lawn_imports_",
    "reports_",
    "stockops_",
)

LEGACY_MIGRATION_APPS = (
    "accounting",
    "accounting_old",
    "books",
    "django_ledger",
    "forbes_lawn",
    "forbes_lawn_accounting",
    "forbes_lawn_billing",
    "forbes_lawn_dashboard",
    "helpers",
    "inventorystock",
    "jobber_sync",
    "lawn_imports",
    "reports",
    "stockops",
)


class Command(BaseCommand):
    help = "Preview or remove legacy accounting and inventory tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Drop the listed legacy tables and clear their migration history.",
        )

    def handle(self, *args, **options):
        tables = sorted(
            table
            for table in connection.introspection.table_names()
            if table.startswith(LEGACY_TABLE_PREFIXES)
        )
        recorder = MigrationRecorder(connection)
        migrations = recorder.migration_qs.filter(
            app__in=LEGACY_MIGRATION_APPS
        )
        migration_count = migrations.count()

        self.stdout.write(f"Legacy tables found: {len(tables)}")
        for table in tables:
            self.stdout.write(f"  {table}")
        self.stdout.write(f"Legacy migration records found: {migration_count}")

        if not options["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    "Preview only. No data changed. Run again with --confirm to remove."
                )
            )
            return

        with transaction.atomic():
            if tables:
                quoted_tables = ", ".join(
                    connection.ops.quote_name(table) for table in tables
                )
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {quoted_tables}")
            migrations.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {len(tables)} legacy tables and {migration_count} migration records."
            )
        )
