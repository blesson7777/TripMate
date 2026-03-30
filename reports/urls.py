from django.urls import path

from reports.views import (
    FuelMonthlySummaryView,
    MonthlyReportPdfView,
    MonthlyReportView,
    TransporterBankDetailsView,
    TransporterBillHeaderDetailsView,
    TransporterBillRecipientDetailView,
    TransporterBillRecipientsView,
    TransporterVehicleBillDetailView,
    TransporterVehicleBillDownloadView,
    TransporterVehicleBillsView,
    VehicleMonthlyRunBillPdfView,
)

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
    path(
        "reports/vehicle-bill/recipients",
        TransporterBillRecipientsView.as_view(),
        name="vehicle-bill-recipients",
    ),
    path(
        "reports/vehicle-bill/recipients/<int:recipient_id>",
        TransporterBillRecipientDetailView.as_view(),
        name="vehicle-bill-recipient-detail",
    ),
    path(
        "reports/vehicle-bill/bank-details",
        TransporterBankDetailsView.as_view(),
        name="vehicle-bill-bank-details",
    ),
    path(
        "reports/vehicle-bill/header-details",
        TransporterBillHeaderDetailsView.as_view(),
        name="vehicle-bill-header-details",
    ),
    path(
        "reports/vehicle-bill/pdf",
        VehicleMonthlyRunBillPdfView.as_view(),
        name="vehicle-monthly-run-bill-pdf",
    ),
    path(
        "reports/vehicle-bill/bills",
        TransporterVehicleBillsView.as_view(),
        name="vehicle-bill-bills",
    ),
    path(
        "reports/vehicle-bill/bills/<int:bill_id>",
        TransporterVehicleBillDetailView.as_view(),
        name="vehicle-bill-bill-detail",
    ),
    path(
        "reports/vehicle-bill/bills/<int:bill_id>/download",
        TransporterVehicleBillDownloadView.as_view(),
        name="vehicle-bill-bill-download",
    ),
]
