from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diesel", "0005_diesel_site_consumption_analysis"),
    ]

    operations = [
        migrations.AddField(
            model_name="dieselsiteconsumptionanalysis",
            name="anomaly_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="dieselsiteconsumptionanalysis",
            name="baseline_cph",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="dieselsiteconsumptionanalysis",
            name="cph_change_percent",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="dieselsiteconsumptionanalysis",
            name="is_cph_anomaly",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="dieselsiteconsumptionanalysis",
            index=models.Index(
                fields=["is_cph_anomaly", "next_fill_date"],
                name="diesel_dies_is_cph_55f944_idx",
            ),
        ),
    ]
