from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fuel", "0009_fuelrecord_dg_hmr_fuelrecord_opening_stock_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fuelrecord",
            name="piu_reading",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="fuelrecord",
            name="dg_hmr",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
