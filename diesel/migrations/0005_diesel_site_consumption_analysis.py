from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("diesel", "0004_diesel_public_entry_link"),
        ("fuel", "0011_fuelrecord_manual_readings_skipped"),
        ("users", "0023_alter_emailotp_purpose"),
    ]

    operations = [
        migrations.CreateModel(
            name="DieselSiteConsumptionAnalysis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("indus_site_id", models.CharField(max_length=64)),
                ("site_name", models.CharField(blank=True, default="", max_length=255)),
                ("previous_fill_date", models.DateField()),
                ("next_fill_date", models.DateField()),
                ("previous_opening_stock", models.DecimalField(decimal_places=2, max_digits=10)),
                ("previous_filled_qty", models.DecimalField(decimal_places=2, max_digits=10)),
                ("available_after_fill", models.DecimalField(decimal_places=2, max_digits=10)),
                ("next_opening_stock", models.DecimalField(decimal_places=2, max_digits=10)),
                ("consumed_qty", models.DecimalField(decimal_places=2, max_digits=10)),
                ("previous_dg_hmr", models.DecimalField(decimal_places=2, max_digits=12)),
                ("next_dg_hmr", models.DecimalField(decimal_places=2, max_digits=12)),
                ("dg_run_hours", models.DecimalField(decimal_places=2, max_digits=12)),
                ("cph", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Consumption per hour")),
                ("previous_piu_reading", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("next_piu_reading", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("piu_delta", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "from_fuel_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consumption_analysis_from_rows",
                        to="fuel.fuelrecord",
                    ),
                ),
                (
                    "partner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="diesel_site_consumption_rows",
                        to="users.transporter",
                    ),
                ),
                (
                    "to_fuel_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consumption_analysis_to_rows",
                        to="fuel.fuelrecord",
                    ),
                ),
                (
                    "tower_site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="consumption_analysis_rows",
                        to="diesel.industowersite",
                    ),
                ),
            ],
            options={
                "ordering": ["-next_fill_date", "-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dieselsiteconsumptionanalysis",
            index=models.Index(fields=["partner", "indus_site_id"], name="diesel_dies_partner_565423_idx"),
        ),
        migrations.AddIndex(
            model_name="dieselsiteconsumptionanalysis",
            index=models.Index(fields=["next_fill_date"], name="diesel_dies_next_fi_e6a075_idx"),
        ),
        migrations.AddIndex(
            model_name="dieselsiteconsumptionanalysis",
            index=models.Index(fields=["cph"], name="diesel_dies_cph_6f0532_idx"),
        ),
        migrations.AddConstraint(
            model_name="dieselsiteconsumptionanalysis",
            constraint=models.UniqueConstraint(
                fields=("from_fuel_record", "to_fuel_record"),
                name="unique_consumption_pair_per_diesel_site",
            ),
        ),
    ]
