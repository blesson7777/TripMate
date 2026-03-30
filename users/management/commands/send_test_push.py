from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from users.models import User, UserDeviceToken
from users.push_service import is_push_enabled, send_push_to_user


class Command(BaseCommand):
    help = "Send a test push notification to a specific user by email."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Target user's email address.")
        parser.add_argument(
            "--variant",
            choices=list(UserDeviceToken.AppVariant.values),
            help="Optional app variant filter (e.g., DRIVER, TRANSPORTER).",
        )
        parser.add_argument("--title", default="TripMate Test", help="Notification title.")
        parser.add_argument(
            "--body",
            default="",
            help="Notification body. Defaults to an auto-generated timestamp message.",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip().lower()
        if not email:
            raise CommandError("Email is required.")

        if not is_push_enabled():
            raise CommandError(
                "Push is disabled (FCM not configured). Set FCM credentials first."
            )

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No user found with email: {email}")

        variant = options.get("variant")
        token_qs = UserDeviceToken.objects.filter(user=user, is_active=True)
        if variant:
            token_qs = token_qs.filter(app_variant=variant)
        token_count = token_qs.count()
        if token_count == 0:
            raise CommandError(
                f"User '{user.username}' has no active push tokens"
                f"{f' for {variant}' if variant else ''}."
            )

        title = (options.get("title") or "").strip() or "TripMate Test"
        body = (options.get("body") or "").strip()
        if not body:
            now = timezone.localtime()
            body = f"Test push at {now:%d %b %Y, %I:%M %p}"

        sent = send_push_to_user(
            user=user,
            title=title,
            body=body,
            data={"kind": "test_push", "sent_at": timezone.now().isoformat()},
            app_variant=variant,
        )

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Targeted {token_count} token(s)"
                    f"{f' ({variant})' if variant else ''} for {email}. "
                    f"Delivered: {sent}."
                )
            )
        )
