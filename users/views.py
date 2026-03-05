from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from users.models import Transporter
from users.serializers import (
    ChangePasswordSerializer,
    DriverProfileSerializer,
    DriverOtpRequestSerializer,
    DriverProfileUpdateSerializer,
    DriverRegisterSerializer,
    LoginSerializer,
    TransporterProfileUpdateSerializer,
    TransporterOtpRequestSerializer,
    TransporterPublicSerializer,
    TransporterRegisterSerializer,
    TransporterSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


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

        refresh = RefreshToken.for_user(user)
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

        refresh = RefreshToken.for_user(user)
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


def _build_profile_payload(user):
    payload = {
        "user": UserSerializer(user).data,
    }

    if hasattr(user, "driver_profile"):
        payload["driver"] = DriverProfileSerializer(user.driver_profile).data

    if hasattr(user, "transporter_profile"):
        payload["transporter"] = TransporterSerializer(user.transporter_profile).data

    return payload


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_build_profile_payload(request.user), status=status.HTTP_200_OK)

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
        payload = _build_profile_payload(result["user"])
        return Response(payload, status=status.HTTP_200_OK)


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
