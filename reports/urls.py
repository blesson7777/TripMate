from django.urls import path

from reports.views import MonthlyReportView

urlpatterns = [
    path("reports/monthly", MonthlyReportView.as_view(), name="monthly-report"),
]
