from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0006_card_payment_match"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="WooPayoutMatch", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("processor", models.CharField(max_length=20)),
            ("gross", models.DecimalField(max_digits=14, decimal_places=2)),
            ("fee", models.DecimalField(max_digits=14, decimal_places=2)),
            ("net", models.DecimalField(max_digits=14, decimal_places=2)),
            ("evidence", models.CharField(max_length=500)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("undone_at", models.DateTimeField(null=True, blank=True)),
            ("order", models.ForeignKey(to="accounting_imports.wooorderimport", on_delete=django.db.models.deletion.PROTECT, related_name="payout_matches")),
            ("bank_row", models.ForeignKey(to="accounting_imports.importrow", on_delete=django.db.models.deletion.PROTECT, related_name="woo_payout_matches")),
            ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="created_woo_payout_matches")),
            ("undone_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="undone_woo_payout_matches")),
        ], options={"constraints": [
            models.UniqueConstraint(fields=["order"], condition=models.Q(undone_at__isnull=True), name="unique_active_woo_order_payout"),
            models.UniqueConstraint(fields=["bank_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_woo_bank_payout"),
        ]}),
    ]
