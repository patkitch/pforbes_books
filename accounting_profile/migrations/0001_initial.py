from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="BusinessProfile",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("display_name", models.CharField(max_length=160)),
                ("legal_name", models.CharField(max_length=160, blank=True)),
                ("entity_type", models.CharField(max_length=20, choices=[
                    ("sole", "Sole proprietorship"), ("llc", "Limited liability company (LLC)"),
                    ("corporation", "Corporation"), ("partnership", "Partnership"), ("other", "Other"),
                ], default="sole")),
                ("tax_id_type", models.CharField(max_length=4, choices=[
                    ("none", "Not provided"), ("ssn", "SSN (last four only)"),
                    ("ein", "EIN (last four only)"),
                ], default="none")),
                ("tax_id_last_four", models.CharField(max_length=4, blank=True)),
                ("address_line_1", models.CharField(max_length=180, blank=True)),
                ("address_line_2", models.CharField(max_length=180, blank=True)),
                ("city", models.CharField(max_length=100, blank=True)),
                ("state", models.CharField(max_length=40, blank=True)),
                ("postal_code", models.CharField(max_length=20, blank=True)),
                ("country", models.CharField(max_length=80, default="United States")),
                ("contact_email", models.EmailField(max_length=254, blank=True)),
                ("contact_phone", models.CharField(max_length=30, blank=True)),
                ("website", models.URLField(max_length=200, blank=True)),
                ("industry", models.CharField(max_length=160, blank=True)),
                ("notes", models.TextField(blank=True)),
            ],
        ),
    ]
