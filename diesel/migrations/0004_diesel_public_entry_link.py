import diesel.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0010_attendancelocationpoint"),
        ("diesel", "0003_daily_route_plans"),
    ]

    operations = [
        migrations.CreateModel(
            name="DieselPublicEntryLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        default=diesel.models.generate_public_diesel_token,
                        max_length=96,
                        unique=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "attendance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="diesel_public_entry_link",
                        to="attendance.attendance",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="dieselpublicentrylink",
            index=models.Index(fields=["token"], name="diesel_dies_token_20bee0_idx"),
        ),
        migrations.AddIndex(
            model_name="dieselpublicentrylink",
            index=models.Index(fields=["expires_at"], name="diesel_dies_expires_f46143_idx"),
        ),
    ]
