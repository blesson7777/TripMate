from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0002_vehicle_vehicle_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="tank_capacity_liters",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
            ),
        ),
    ]
