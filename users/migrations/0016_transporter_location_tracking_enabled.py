from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_user_session_revoked_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transporter",
            name="location_tracking_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
