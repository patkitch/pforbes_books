from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounting_profile", "0001_initial")]
    operations = [
        migrations.AddField(model_name="businessprofile", name="legal_address_line_1", field=models.CharField(max_length=180, blank=True)),
        migrations.AddField(model_name="businessprofile", name="legal_address_line_2", field=models.CharField(max_length=180, blank=True)),
        migrations.AddField(model_name="businessprofile", name="legal_city", field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name="businessprofile", name="legal_state", field=models.CharField(max_length=40, blank=True)),
        migrations.AddField(model_name="businessprofile", name="legal_postal_code", field=models.CharField(max_length=20, blank=True)),
        migrations.AddField(model_name="businessprofile", name="legal_country", field=models.CharField(max_length=80, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_email", field=models.EmailField(max_length=254, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_address_line_1", field=models.CharField(max_length=180, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_address_line_2", field=models.CharField(max_length=180, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_city", field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_state", field=models.CharField(max_length=40, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_postal_code", field=models.CharField(max_length=20, blank=True)),
        migrations.AddField(model_name="businessprofile", name="customer_country", field=models.CharField(max_length=80, blank=True)),
        migrations.AddField(model_name="businessprofile", name="branding_logo_url", field=models.URLField(blank=True)),
    ]
