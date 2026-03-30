from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from users.auth_events import (
    log_forced_logout,
    log_login_success,
    log_normal_logout,
    revoke_user_sessions,
)
from users.models import (
    AccountDeletionRequest,
    AdminBroadcastNotification,
    AppRelease,
    DriverNotification,
    FeatureToggleLog,
    Transporter,
    TransporterNotification,
    UserDeviceToken,
    User,
)
from users.notification_utils import (
    create_diesel_module_toggled_notifications,
    ensure_time_based_driver_notifications,
    ensure_time_based_transporter_notifications,
)
from users.permissions import IsAdminRole
from users.serializers import (
    AdminDieselModuleToggleSerializer,
    ChangePasswordSerializer,
    DriverNotificationSerializer,
    DriverLoginOtpRequestSerializer,
    DriverLoginOtpVerifySerializer,
    DriverProfileSerializer,
    DriverOtpRequestSerializer,
    ProfileAccountDeletionSerializer,
    ProfileAccountDeletionOtpRequestSerializer,
    DriverProfileUpdateSerializer,
    DriverRegisterSerializer,
    LoginSerializer,
    PasswordResetOtpRequestSerializer,
    ProfileEmailChangeOtpRequestSerializer,
    ResetPasswordWithOtpSerializer,
    SessionTokenRefreshSerializer,
    TransporterLoginOtpRequestSerializer,
    TransporterLoginOtpVerifySerializer,
    TransporterProfileUpdateSerializer,
    TransporterOtpRequestSerializer,
    TransporterNotificationSerializer,
    TransporterPublicSerializer,
    TransporterRegisterSerializer,
    TransporterSerializer,
    UserSerializer,
)


def _build_refresh_token(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["username"] = user.username
    refresh["session_nonce"] = str(user.session_nonce)
    return refresh


def _build_login_payload(user):
    refresh = _build_refresh_token(user)
    payload = {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": UserSerializer(user).data,
    }
    if hasattr(user, "transporter_profile"):
        payload["transporter_id"] = user.transporter_profile.id
        payload["diesel_tracking_enabled"] = (
            user.transporter_profile.diesel_tracking_enabled
        )
        payload["diesel_readings_enabled"] = (
            user.transporter_profile.diesel_readings_enabled
        )
        payload["location_tracking_enabled"] = (
            user.transporter_profile.location_tracking_enabled
        )
    if hasattr(user, "driver_profile"):
        payload["driver_id"] = user.driver_profile.id
        driver_transporter = user.driver_profile.transporter
        payload["diesel_tracking_enabled"] = bool(
            driver_transporter and driver_transporter.diesel_tracking_enabled
        )
        payload["diesel_readings_enabled"] = bool(
            driver_transporter and driver_transporter.diesel_readings_enabled
        )
        payload["location_tracking_enabled"] = bool(
            driver_transporter and driver_transporter.location_tracking_enabled
        )
    return payload


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            user_id = (response.data or {}).get("user", {}).get("id")
            user = User.objects.filter(pk=user_id).first() if user_id else None
            if user is not None:
                log_login_success(request, user)
        return response


class SessionRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = SessionTokenRefreshSerializer


class TransporterPublicListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TransporterPublicSerializer

    def get_queryset(self):
        return Transporter.objects.select_related("user").all()


class TransporterRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TransporterRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = serializer.save()
        user = created["user"]
        transporter = created["transporter"]

        refresh = _build_refresh_token(user)
        payload = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
            "transporter_id": transporter.id,
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class DriverRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DriverRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = serializer.save()
        user = created["user"]
        driver = created["driver"]

        refresh = _build_refresh_token(user)
        payload = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
            "driver_id": driver.id,
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class TransporterOtpRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TransporterOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class DriverOtpRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DriverOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class DriverLoginOtpRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DriverLoginOtpRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to your email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class DriverLoginOtpVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = DriverLoginOtpVerifySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        revoke_user_sessions(user)
        payload = _build_login_payload(user)
        log_login_success(request, user)
        return Response(payload, status=status.HTTP_200_OK)


class TransporterLoginOtpRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TransporterLoginOtpRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to your email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class TransporterLoginOtpVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TransporterLoginOtpVerifySerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        revoke_user_sessions(user)
        payload = _build_login_payload(user)
        log_login_success(request, user)
        return Response(payload, status=status.HTTP_200_OK)


class PasswordResetOtpRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordWithOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password reset successful. Please login."},
            status=status.HTTP_200_OK,
        )


class PushTokenRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = str(request.data.get("token", "")).strip()
        if not token:
            return Response(
                {"detail": "token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_variant = str(
            request.data.get("app_variant", UserDeviceToken.AppVariant.GENERIC)
        ).strip().upper()
        if app_variant not in UserDeviceToken.AppVariant.values:
            return Response(
                {
                    "detail": (
                        "Invalid app_variant. Use DRIVER, TRANSPORTER, or GENERIC."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        platform = str(
            request.data.get("platform", UserDeviceToken.Platform.ANDROID)
        ).strip().upper()
        if platform not in UserDeviceToken.Platform.values:
            return Response(
                {"detail": "Invalid platform. Use ANDROID, IOS, or WEB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_version = str(request.data.get("app_version", "")).strip()
        app_build_number_raw = str(request.data.get("app_build_number", "")).strip()
        app_build_number = None
        if app_build_number_raw:
            if not app_build_number_raw.isdigit():
                return Response(
                    {"detail": "app_build_number must be a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            app_build_number = int(app_build_number_raw)

        device, created = UserDeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "user": request.user,
                "app_version": app_version,
                "app_build_number": app_build_number,
                "app_variant": app_variant,
                "platform": platform,
                "is_active": True,
            },
        )
        UserDeviceToken.objects.filter(
            user=request.user,
            app_variant=app_variant,
            is_active=True,
        ).exclude(pk=device.pk).update(is_active=False)
        return Response(
            {
                "status": "success",
                "created": created,
                "device_token_id": device.id,
            },
            status=status.HTTP_200_OK,
        )


class AppUpdateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, app_variant: str):
        normalized = str(app_variant or "").strip().upper()
        if normalized not in {"DRIVER", "TRANSPORTER"}:
            return Response(
                {"detail": "Invalid app variant. Use driver or transporter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        release = (
            AppRelease.objects.filter(
                app_variant=normalized,
                is_active=True,
            )
            .order_by("-build_number", "-published_at", "-created_at")
            .first()
        )

        if release is None:
            return Response(
                {
                    "app_variant": normalized.lower(),
                    "available": False,
                    "latest_version": None,
                    "latest_build_number": None,
                    "apk_url": "",
                    "force_update": False,
                    "message": "No published release is available.",
                },
                status=status.HTTP_200_OK,
            )

        apk_url = request.build_absolute_uri(release.apk_file.url)
        return Response(
            {
                "app_variant": normalized.lower(),
                "available": True,
                "latest_version": release.version_name,
                "latest_build_number": release.build_number,
                "apk_url": apk_url,
                "force_update": release.force_update,
                "message": release.message
                or f"New {release.get_app_variant_display()} update available.",
                "published_at": release.published_at or release.created_at,
            },
            status=status.HTTP_200_OK,
        )


class PushTokenUnregisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = str(request.data.get("token", "")).strip()
        queryset = UserDeviceToken.objects.filter(user=request.user, is_active=True)
        if token:
            queryset = queryset.filter(token=token)

        updated_count = queryset.update(is_active=False)
        return Response(
            {
                "status": "success",
                "updated_count": updated_count,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = str(request.data.get("refresh", "")).strip()
        push_token = str(request.data.get("token", "")).strip()

        blacklisted = False
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
                blacklisted = True
            except Exception:
                blacklisted = False

        deactivated_tokens = 0
        if push_token:
            deactivated_tokens = UserDeviceToken.objects.filter(
                user=request.user,
                token=push_token,
                is_active=True,
            ).update(is_active=False)

        log_normal_logout(
            request,
            request.user,
            reason=(
                "API logout completed."
                if blacklisted
                else "API logout completed without refresh blacklist."
            ),
        )
        return Response(
            {
                "status": "success",
                "refresh_blacklisted": blacklisted,
                "deactivated_tokens": deactivated_tokens,
            },
            status=status.HTTP_200_OK,
        )


class AdminForceLogoutView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, user_id: int):
        target_user = User.objects.filter(pk=user_id).first()
        if target_user is None:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if target_user == request.user:
            return Response(
                {"detail": "You cannot force logout your own account here."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        revoke_user_sessions(target_user)
        log_forced_logout(
            request,
            target_user,
            reason=f"Admin {request.user.username} forced logout.",
        )
        return Response(
            {"status": "success", "detail": "User sessions revoked."},
            status=status.HTTP_200_OK,
        )


class AdminPartnerDieselToggleView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = AdminDieselModuleToggleSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        transporter = serializer.context["target_transporter"]
        enabled = bool(serializer.validated_data["enabled"])
        if transporter.diesel_tracking_enabled != enabled:
            transporter.diesel_tracking_enabled = enabled
            update_fields = ["diesel_tracking_enabled"]
            if not enabled and transporter.diesel_readings_enabled:
                transporter.diesel_readings_enabled = False
                update_fields.append("diesel_readings_enabled")
            transporter.save(update_fields=update_fields)
            FeatureToggleLog.objects.create(
                admin=request.user,
                partner=transporter,
                feature_name="diesel_module",
                action=(
                    FeatureToggleLog.Action.ENABLED
                    if enabled
                    else FeatureToggleLog.Action.DISABLED
                ),
            )
            create_diesel_module_toggled_notifications(
                transporter=transporter,
                enabled=enabled,
            )

        return Response(
            {
                "status": "success",
                "partner_id": transporter.id,
                "diesel_tracking_enabled": transporter.diesel_tracking_enabled,
            },
            status=status.HTTP_200_OK,
        )


def _build_profile_payload(user, *, request=None):
    serializer_context = {"request": request} if request is not None else None
    payload = {
        "user": UserSerializer(user, context=serializer_context).data,
    }

    if hasattr(user, "driver_profile"):
        payload["driver"] = DriverProfileSerializer(
            user.driver_profile,
            context=serializer_context,
        ).data

    if hasattr(user, "transporter_profile"):
        payload["transporter"] = TransporterSerializer(
            user.transporter_profile,
            context=serializer_context,
        ).data

    return payload


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            _build_profile_payload(request.user, request=request),
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        user = request.user
        context = {"request": request}

        if hasattr(user, "driver_profile"):
            serializer = DriverProfileUpdateSerializer(
                instance=user.driver_profile,
                data=request.data,
                partial=True,
                context=context,
            )
        elif hasattr(user, "transporter_profile"):
            serializer = TransporterProfileUpdateSerializer(
                instance=user.transporter_profile,
                data=request.data,
                partial=True,
                context=context,
            )
        else:
            return Response(
                {"detail": "Profile is not available for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = _build_profile_payload(result["user"], request=request)
        return Response(payload, status=status.HTTP_200_OK)


class ProfileEmailChangeOtpRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProfileEmailChangeOtpRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class ProfileAccountDeletionOtpRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProfileAccountDeletionOtpRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        payload = {
            "detail": "OTP sent to email.",
            "email": result["email"],
        }
        if result.get("debug_otp"):
            payload["debug_otp"] = result["debug_otp"]
        return Response(payload, status=status.HTTP_200_OK)


class ProfileAccountDeletionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProfileAccountDeletionSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        log_normal_logout(
            request,
            request.user,
            reason="Self-service account deletion completed after email OTP validation.",
        )
        revoked_at = revoke_user_sessions(request.user)
        serializer.save(revoked_at=revoked_at)
        return Response(
            {"detail": "Account deleted successfully. You have been signed out."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )


def _broadcast_items_for_user(user, limit=10):
    queryset = AdminBroadcastNotification.objects.filter(is_active=True)
    if user.role == User.Role.DRIVER:
        queryset = queryset.filter(
            audience__in=[
                AdminBroadcastNotification.Audience.ALL,
                AdminBroadcastNotification.Audience.DRIVER,
            ]
        )
    elif user.role == User.Role.TRANSPORTER:
        queryset = queryset.filter(
            audience__in=[
                AdminBroadcastNotification.Audience.ALL,
                AdminBroadcastNotification.Audience.TRANSPORTER,
            ]
        )
    else:
        queryset = queryset.filter(audience=AdminBroadcastNotification.Audience.ALL)

    announcements = list(queryset.order_by("-created_at")[:limit])
    return [
        {
            "id": announcement.id + 1_000_000,
            "notification_type": "SYSTEM_ALERT",
            "title": announcement.title,
            "message": announcement.message,
            "driver": None,
            "driver_name": None,
            "trip": None,
            "is_read": True,
            "created_at": announcement.created_at.isoformat(),
        }
        for announcement in announcements
    ]


class TransporterNotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.TRANSPORTER:
            return Response(
                {"detail": "Only transporter can view notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ensure_time_based_transporter_notifications(transporter)

        unread_only = request.query_params.get("unread_only", "false").lower() == "true"
        try:
            limit = int(request.query_params.get("limit", 30))
        except ValueError:
            limit = 30
        limit = min(max(limit, 1), 100)

        queryset = TransporterNotification.objects.filter(transporter=transporter)
        if unread_only:
            queryset = queryset.filter(is_read=False)

        items = queryset.select_related("driver", "driver__user", "trip")[:limit]
        unread_count = TransporterNotification.objects.filter(
            transporter=transporter,
            is_read=False,
        ).count()
        transporter_items = TransporterNotificationSerializer(items, many=True).data
        broadcast_items = (
            _broadcast_items_for_user(request.user, limit=10) if not unread_only else []
        )
        merged = [*transporter_items, *broadcast_items]
        merged.sort(
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )

        return Response(
            {
                "unread_count": unread_count,
                "items": merged[:limit],
            },
            status=status.HTTP_200_OK,
        )


class TransporterNotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != User.Role.TRANSPORTER:
            return Response(
                {"detail": "Only transporter can update notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )
        transporter = getattr(request.user, "transporter_profile", None)
        if transporter is None:
            return Response(
                {"detail": "Transporter profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification_id = request.data.get("notification_id")
        queryset = TransporterNotification.objects.filter(
            transporter=transporter,
            is_read=False,
        )
        if notification_id is not None:
            queryset = queryset.filter(id=notification_id)

        updated_count = queryset.update(is_read=True)
        unread_count = TransporterNotification.objects.filter(
            transporter=transporter,
            is_read=False,
        ).count()
        return Response(
            {
                "updated_count": updated_count,
                "unread_count": unread_count,
            },
            status=status.HTTP_200_OK,
        )


class DriverNotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.DRIVER:
            return Response(
                {"detail": "Only driver can view notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )
        driver = getattr(request.user, "driver_profile", None)
        if driver is None:
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ensure_time_based_driver_notifications(driver)

        unread_only = request.query_params.get("unread_only", "false").lower() == "true"
        try:
            limit = int(request.query_params.get("limit", 30))
        except ValueError:
            limit = 30
        limit = min(max(limit, 1), 100)

        queryset = DriverNotification.objects.filter(driver=driver)
        if unread_only:
            queryset = queryset.filter(is_read=False)

        driver_items = DriverNotificationSerializer(
            queryset.select_related("driver", "driver__user", "trip")[:limit],
            many=True,
        ).data
        broadcast_items = (
            _broadcast_items_for_user(request.user, limit=10) if not unread_only else []
        )
        merged = [*driver_items, *broadcast_items]
        merged.sort(
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
        unread_count = DriverNotification.objects.filter(
            driver=driver,
            is_read=False,
        ).count()
        return Response(
            {
                "unread_count": unread_count,
                "items": merged[:limit],
            },
            status=status.HTTP_200_OK,
        )


class DriverNotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != User.Role.DRIVER:
            return Response(
                {"detail": "Only driver can update notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )
        driver = getattr(request.user, "driver_profile", None)
        if driver is None:
            return Response(
                {"detail": "Driver profile does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification_id = request.data.get("notification_id")
        queryset = DriverNotification.objects.filter(
            driver=driver,
            is_read=False,
        )
        if notification_id is not None:
            queryset = queryset.filter(id=notification_id)

        updated_count = queryset.update(is_read=True)
        unread_count = DriverNotification.objects.filter(
            driver=driver,
            is_read=False,
        ).count()
        return Response(
            {
                "updated_count": updated_count,
                "unread_count": unread_count,
            },
            status=status.HTTP_200_OK,
        )
