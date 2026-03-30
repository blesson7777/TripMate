from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from tripmate import public_views

urlpatterns = [
    path("", lambda request: redirect("/admin/")),
    path("privacy-policy/", public_views.privacy_policy, name="privacy-policy"),
    path("account-deletion/", public_views.account_deletion, name="account-deletion"),
    path("admin/", include("tripmate.admin_dashboard_urls")),
    path("django-admin/", admin.site.urls),
    path("api/", include("api.routes")),
    path("api/", include("users.urls")),
    path("api/", include("vehicles.urls")),
    path("api/", include("drivers.urls")),
    path("api/", include("attendance.urls")),
    path("api/", include("trips.urls")),
    path("api/", include("fuel.urls")),
    path("api/", include("diesel.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("salary.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
