from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("drivers", "0004_driver_default_service"),
    ]

    operations = [
        migrations.AddField(
            model_name="driver",
            name="monthly_salary",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
