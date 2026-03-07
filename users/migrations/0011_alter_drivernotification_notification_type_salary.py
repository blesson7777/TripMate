from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_alter_drivernotification_notification_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="drivernotification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("ATTENDANCE_MARK_UPDATED", "Attendance Mark Updated"),
                    ("START_DAY_MISSED", "Start Day Missed"),
                    ("TRIP_OVERDUE", "Trip Overdue"),
                    ("FUEL_ANOMALY", "Fuel Anomaly"),
                    ("DIESEL_MODULE_TOGGLED", "Diesel Module Toggled"),
                    ("MONTH_END_REMINDER", "Month End Reminder"),
                    ("WELCOME_ALLOCATED", "Welcome Allocated"),
                    ("SALARY_PAID", "Salary Paid"),
                    ("ADVANCE_UPDATED", "Advance Updated"),
                    ("SYSTEM", "System"),
                ],
                max_length=40,
            ),
        ),
    ]
