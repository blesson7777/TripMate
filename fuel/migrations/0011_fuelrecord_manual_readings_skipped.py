from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fuel", "0010_remove_diesel_reading_digit_limit"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelrecord",
            name="manual_readings_skipped",
            field=models.BooleanField(default=False),
        ),
    ]
