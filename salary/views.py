from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from salary.models import DriverSalaryAdvance
from salary.serializers import (
    DriverMonthlySalaryUpdateSerializer,
    DriverSalaryAdvanceSerializer,
    DriverSalaryAdvanceUpsertSerializer,
    DriverSalaryPaySerializer,
    DriverSalaryMonthRowSerializer,
    SalaryMonthSummarySerializer,
)
from salary.utils import calculate_salary_month_for_transporter, calculate_salary_summary_for_driver
from users.permissions import IsTransporterRole

from drivers.models import Driver


class SalaryMonthSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def get(self, request):
        today = timezone.localdate()
        try:
            month = int(request.query_params.get("month", today.month))
            year = int(request.query_params.get("year", today.year))
        except ValueError:
            return Response(
                {"detail": "Month and year must be numeric values."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = calculate_salary_month_for_transporter(
            transporter=request.user.transporter_profile,
            month=month,
            year=year,
            today=today,
        )
        serializer = SalaryMonthSummarySerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DriverMonthlySalaryUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def patch(self, request, driver_id: int):
        driver = (
            Driver.objects.select_related("user")
            .filter(
                id=driver_id,
                transporter=request.user.transporter_profile,
                is_active=True,
            )
            .first()
        )
        if driver is None:
            return Response(
                {"detail": "Driver not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DriverMonthlySalaryUpdateSerializer(data=request.data, context={"driver": driver})
        serializer.is_valid(raise_exception=True)
        driver = serializer.save()
        return Response(
            {
                "detail": "Monthly salary updated successfully.",
                "driver_id": driver.id,
                "monthly_salary": driver.monthly_salary,
            },
            status=status.HTTP_200_OK,
        )


class DriverSalaryPayView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def post(self, request):
        serializer = DriverSalaryPaySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        row = calculate_salary_summary_for_driver(
            driver=payment.driver,
            month=payment.salary_month,
            year=payment.salary_year,
            cl_count=payment.cl_count,
            payment=payment,
            today=timezone.localdate(),
        )
        return Response(
            {
                "detail": "Salary paid successfully.",
                "row": DriverSalaryMonthRowSerializer(row).data,
            },
            status=status.HTTP_201_CREATED,
        )


class DriverSalaryAdvanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]
    serializer_class = DriverSalaryAdvanceSerializer

    def get_queryset(self):
        queryset = DriverSalaryAdvance.objects.select_related(
            "driver",
            "driver__user",
            "recorded_by",
            "settled_payment",
        ).filter(transporter=self.request.user.transporter_profile)
        driver_id = self.request.query_params.get("driver_id")
        month = self.request.query_params.get("month")
        year = self.request.query_params.get("year")
        if driver_id and driver_id.isdigit():
            queryset = queryset.filter(driver_id=int(driver_id))
        if month and year and month.isdigit() and year.isdigit():
            queryset = queryset.filter(
                advance_date__month=int(month),
                advance_date__year=int(year),
            )
        return queryset

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DriverSalaryAdvanceUpsertSerializer
        return DriverSalaryAdvanceSerializer

    def post(self, request, *args, **kwargs):
        serializer = DriverSalaryAdvanceUpsertSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        advance = serializer.save()
        return Response(
            {
                "detail": "Advance saved successfully.",
                "advance": DriverSalaryAdvanceSerializer(advance).data,
            },
            status=status.HTTP_201_CREATED,
        )


class DriverSalaryAdvanceDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTransporterRole]

    def patch(self, request, advance_id: int):
        advance = (
            DriverSalaryAdvance.objects.select_related("driver", "driver__user")
            .filter(id=advance_id, transporter=request.user.transporter_profile)
            .first()
        )
        if advance is None:
            return Response(
                {"detail": "Advance not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = DriverSalaryAdvanceUpsertSerializer(
            data=request.data,
            context={"request": request, "instance": advance},
        )
        serializer.is_valid(raise_exception=True)
        advance = serializer.save()
        return Response(
            {
                "detail": "Advance updated successfully.",
                "advance": DriverSalaryAdvanceSerializer(advance).data,
            },
            status=status.HTTP_200_OK,
        )
