from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("website", models.URLField(blank=True)),
                ("address1", models.CharField(blank=True, max_length=200)),
                ("address2", models.CharField(blank=True, max_length=200)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=100)),
                ("postal_code", models.CharField(blank=True, max_length=24)),
                ("country", models.CharField(blank=True, default="United States", max_length=80)),
                ("notes", models.TextField(blank=True)),
                ("default_account_number", models.CharField(blank=True, help_text="Suggested account number only; never auto-post.", max_length=4)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("name", "pk")},
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("kind", models.CharField(
                    choices=[("person", "Individual"), ("organization", "Organization")],
                    default="person", max_length=20
                )),
                ("billing_address1", models.CharField(blank=True, max_length=200)),
                ("billing_address2", models.CharField(blank=True, max_length=200)),
                ("billing_city", models.CharField(blank=True, max_length=100)),
                ("billing_state", models.CharField(blank=True, max_length=100)),
                ("billing_postal_code", models.CharField(blank=True, max_length=24)),
                ("billing_country", models.CharField(blank=True, max_length=80)),
                ("shipping_address1", models.CharField(blank=True, max_length=200)),
                ("shipping_address2", models.CharField(blank=True, max_length=200)),
                ("shipping_city", models.CharField(blank=True, max_length=100)),
                ("shipping_state", models.CharField(blank=True, max_length=100)),
                ("shipping_postal_code", models.CharField(blank=True, max_length=24)),
                ("shipping_country", models.CharField(blank=True, max_length=80)),
                ("woo_customer_id", models.PositiveBigIntegerField(blank=True, help_text="WooCommerce registered customer ID. Never use guest ID 0.", null=True, unique=True)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("name", "pk")},
        ),
        migrations.CreateModel(
            name="TransactionParty",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("journal_entry_id", models.PositiveBigIntegerField(db_index=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("vendor", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="transaction_links", to="accounting_contacts.vendor"
                )),
                ("customer", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="transaction_links", to="accounting_contacts.customer"
                )),
            ],
            options={"ordering": ("-pk",)},
        ),
        migrations.CreateModel(
            name="Receipt",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("receipt_type", models.CharField(
                    choices=[("purchase", "Purchase receipt"), ("sale", "Sales receipt"), ("refund", "Refund documentation"), ("other", "Other document")], max_length=20
                )),
                ("date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("journal_entry_id", models.PositiveBigIntegerField(blank=True, db_index=True, null=True)),
                ("source", models.CharField(default="manual", max_length=40)),
                ("source_reference", models.CharField(blank=True, max_length=180)),
                ("attachment", models.FileField(blank=True, upload_to="accounting_receipts/%Y/%m/")),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("vendor", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="receipts", to="accounting_contacts.vendor"
                )),
                ("customer", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="receipts", to="accounting_contacts.customer"
                )),
            ],
            options={"ordering": ("-date", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.UniqueConstraint(
                fields=("source", "source_reference"),
                condition=~models.Q(source_reference=""),
                name="ac_contact_unique_receipt_source",
            ),
        ),
    ]
