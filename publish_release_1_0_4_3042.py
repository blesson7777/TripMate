from pathlib import Path

from django.core.files import File
from django.utils import timezone

from users.models import AppRelease

RELEASES = [
    (
        "DRIVER",
        "1.0.4",
        3042,
        "/home/ubuntu/app-driver-1.0.4-3042.apk",
        "tripmate_driver_1.0.4_3042.apk",
        "TripMate Driver 1.0.4 (3042) is available.",
    ),
    (
        "TRANSPORTER",
        "1.0.4",
        3042,
        "/home/ubuntu/app-transporter-1.0.4-3042.apk",
        "tripmate_transporter_1.0.4_3042.apk",
        "TripMate Transporter 1.0.4 (3042) is available.",
    ),
]


def publish_release(
    *,
    app_variant: str,
    version_name: str,
    build_number: int,
    source_path: str,
    file_name: str,
    message: str,
):
    AppRelease.objects.filter(
        app_variant=app_variant,
        version_name=version_name,
        build_number=build_number,
    ).delete()

    release = AppRelease(
        app_variant=app_variant,
        version_name=version_name,
        build_number=build_number,
        force_update=False,
        message=message,
        is_active=True,
        published_at=timezone.now(),
        push_sent_at=None,
        uploaded_by=None,
    )

    with Path(source_path).open("rb") as handle:
        release.apk_file.save(file_name, File(handle), save=False)

    release.save()
    AppRelease.objects.filter(app_variant=app_variant).exclude(pk=release.pk).update(
        is_active=False
    )
    print(
        f"{app_variant}: {release.version_name} ({release.build_number}) -> {release.apk_file.name}"
    )


for app_variant, version_name, build_number, source_path, file_name, message in RELEASES:
    publish_release(
        app_variant=app_variant,
        version_name=version_name,
        build_number=build_number,
        source_path=source_path,
        file_name=file_name,
        message=message,
    )

