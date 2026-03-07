from django.urls import path

from reports.views import FuelMonthlySummaryView, MonthlyReportPdfView, MonthlyReportView

urlpatterns = [
    path("reports/monthly", MonthlyReportView.as_view(), name="monthly-report"),
    path("reports/monthly/pdf", MonthlyReportPdfView.as_view(), name="monthly-report-pdf"),
    path(
        "reports/monthly/pdf/",
        MonthlyReportPdfView.as_view(),
        name="monthly-report-pdf-slash",
    ),
    path(
        "reports/fuel-monthly",
        FuelMonthlySummaryView.as_view(),
        name="fuel-monthly-summary",
    ),
]
