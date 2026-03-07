from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_apprelease"),
    ]

    operations = [
        migrations.AddField(
            model_name="transporter",
            name="salary_auto_email_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
