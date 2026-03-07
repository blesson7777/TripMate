from django.urls import path

from salary.views import (
    DriverMonthlySalaryUpdateView,
    DriverSalaryAdvanceDetailView,
    DriverSalaryAdvanceListCreateView,
    DriverSalaryPayView,
    SalaryMonthSummaryView,
)

urlpatterns = [
    path("salary/monthly", SalaryMonthSummaryView.as_view(), name="salary-monthly"),
    path(
        "salary/driver/<int:driver_id>/monthly-salary",
        DriverMonthlySalaryUpdateView.as_view(),
        name="driver-monthly-salary-update",
    ),
    path("salary/pay", DriverSalaryPayView.as_view(), name="driver-salary-pay"),
    path("salary/advances", DriverSalaryAdvanceListCreateView.as_view(), name="salary-advances"),
    path(
        "salary/advances/<int:advance_id>",
        DriverSalaryAdvanceDetailView.as_view(),
        name="salary-advance-detail",
    ),
]
