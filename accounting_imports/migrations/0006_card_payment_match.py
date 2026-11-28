from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0005_import_undo"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="CardPaymentMatch", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("undone_at", models.DateTimeField(null=True, blank=True)),
            ("bank_row", models.ForeignKey(to="accounting_imports.importrow", on_delete=django.db.models.deletion.PROTECT, related_name="bank_payment_matches")),
            ("card_row", models.ForeignKey(to="accounting_imports.importrow", on_delete=django.db.models.deletion.PROTECT, related_name="card_payment_matches")),
            ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="created_payment_matches")),
            ("undone_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="undone_payment_matches")),
        ], options={"constraints": [
            models.UniqueConstraint(fields=["bank_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_bank_payment_match"),
            models.UniqueConstraint(fields=["card_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_card_payment_match"),
        ]}),
    ]
