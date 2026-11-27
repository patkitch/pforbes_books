from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("accounting_imports", "0009_stripe_review"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="StripePayoutMatch", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("payout_id", models.CharField(max_length=180)),
            ("gross", models.DecimalField(max_digits=14, decimal_places=2)),
            ("fee", models.DecimalField(max_digits=14, decimal_places=2)),
            ("net", models.DecimalField(max_digits=14, decimal_places=2)),
            ("evidence", models.CharField(max_length=500)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("undone_at", models.DateTimeField(null=True, blank=True)),
            ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payout_matches", to="accounting_imports.stripepaymentimport")),
            ("bank_row", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stripe_payout_matches", to="accounting_imports.importrow")),
            ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_stripe_payout_matches", to=settings.AUTH_USER_MODEL)),
            ("undone_by", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="undone_stripe_payout_matches", to=settings.AUTH_USER_MODEL)),
        ], options={"constraints":[
            models.UniqueConstraint(fields=["payment"], condition=models.Q(undone_at__isnull=True), name="unique_active_stripe_payment"),
            models.UniqueConstraint(fields=["payout_id"], condition=models.Q(undone_at__isnull=True), name="unique_active_stripe_payout"),
            models.UniqueConstraint(fields=["bank_row"], condition=models.Q(undone_at__isnull=True), name="unique_active_stripe_bank"),
        ]}),
    ]
