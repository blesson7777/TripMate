import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_mark_transporters(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    DriverDailyAttendanceMark = apps.get_model("attendance", "DriverDailyAttendanceMark")
    Driver = apps.get_model("drivers", "Driver")
    Transporter = apps.get_model("users", "Transporter")
    db_alias = schema_editor.connection.alias

    for mark in DriverDailyAttendanceMark.objects.using(db_alias).filter(
        transporter_id__isnull=True
    ):
        transporter_id = (
            Attendance.objects.using(db_alias)
            .filter(driver_id=mark.driver_id, date=mark.date)
            .values_list("vehicle__transporter_id", flat=True)
            .first()
        )
        if transporter_id is None and mark.marked_by_id is not None:
            transporter_id = (
                Transporter.objects.using(db_alias)
                .filter(user_id=mark.marked_by_id)
                .values_list("id", flat=True)
                .first()
            )
        if transporter_id is None:
            transporter_id = (
                Driver.objects.using(db_alias)
                .filter(id=mark.driver_id)
                .values_list("transporter_id", flat=True)
                .first()
            )
        if transporter_id is None:
            continue
        DriverDailyAttendanceMark.objects.using(db_alias).filter(id=mark.id).update(
            transporter_id=transporter_id
        )


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0008_remove_attendance_unique_driver_attendance_per_day'),
        ('drivers', '0006_driver_joined_transporter_at'),
        ('users', '0011_alter_drivernotification_notification_type_salary'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='driverdailyattendancemark',
            name='unique_driver_mark_per_day',
        ),
        migrations.AddField(
            model_name='driverdailyattendancemark',
            name='transporter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='daily_attendance_marks', to='users.transporter'),
        ),
        migrations.RunPython(backfill_mark_transporters, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='driverdailyattendancemark',
            constraint=models.UniqueConstraint(fields=('driver', 'transporter', 'date'), name='unique_driver_mark_per_day_per_transporter'),
        ),
    ]
