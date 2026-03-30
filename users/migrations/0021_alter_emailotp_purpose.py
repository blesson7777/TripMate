from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0020_alter_emailotp_purpose"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailotp",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("TRANSPORTER_SIGNUP", "Transporter Signup"),
                    ("DRIVER_SIGNUP", "Driver Signup"),
                    ("DRIVER_ALLOCATION", "Driver Allocation"),
                    ("PASSWORD_RESET", "Password Reset"),
                    ("PROFILE_EMAIL_CHANGE", "Profile Email Change"),
                    ("ACCOUNT_DELETION", "Account Deletion"),
                ],
                max_length=40,
            ),
        ),
    ]
