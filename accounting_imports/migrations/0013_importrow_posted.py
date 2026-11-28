from django.db import migrations,models

class Migration(migrations.Migration):
    dependencies=[("accounting_imports","0012_stripe_adjustment")]
    operations=[migrations.AlterField(model_name="importrow",name="status",field=models.CharField(max_length=12,default="pending",choices=[("pending","Pending"),("excluded","Excluded"),("reviewed","Reviewed — not posted"),("posted","Posted")]))]
