from datetime import datetime

from django.utils import timezone
from django.db import migrations, models


def backfill_joined_transporter_at(apps, schema_editor):
    Driver = apps.get_model("drivers", "Driver")
    db_alias = schema_editor.connection.alias
    fallback_joined_at = timezone.make_aware(datetime(2016, 3, 1, 0, 0, 0))

    Driver.objects.using(db_alias).filter(
        transporter_id__isnull=False,
        joined_transporter_at__isnull=True,
    ).update(joined_transporter_at=fallback_joined_at)


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0005_driver_monthly_salary'),
    ]

    operations = [
        migrations.AddField(
            model_name='driver',
            name='joined_transporter_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_joined_transporter_at, migrations.RunPython.noop),
    ]
