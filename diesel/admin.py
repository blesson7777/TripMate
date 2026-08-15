from django.contrib import admin

from diesel.models import DieselSiteConsumptionAnalysis, IndusTowerSite


@admin.register(IndusTowerSite)
class IndusTowerSiteAdmin(admin.ModelAdmin):
    list_display = ("indus_site_id", "site_name", "partner", "latitude", "longitude")
    search_fields = ("indus_site_id", "site_name", "partner__company_name")
    list_filter = ("partner",)


@admin.register(DieselSiteConsumptionAnalysis)
class DieselSiteConsumptionAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "indus_site_id",
        "site_name",
        "previous_fill_date",
        "next_fill_date",
        "consumed_qty",
        "dg_run_hours",
        "cph",
        "baseline_cph",
        "cph_change_percent",
        "is_cph_anomaly",
    )
    search_fields = ("indus_site_id", "site_name", "partner__company_name")
    list_filter = ("partner", "is_cph_anomaly", "next_fill_date")
