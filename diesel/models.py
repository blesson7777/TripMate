from django.core.exceptions import ValidationError
from django.db import models

from diesel.site_utils import validate_indus_site_id, validate_site_name


class IndusTowerSite(models.Model):
    partner = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="indus_tower_sites",
    )
    indus_site_id = models.CharField(max_length=64)
    site_name = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["site_name", "indus_site_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["partner", "indus_site_id"],
                name="unique_indus_site_id_per_partner",
            )
        ]
        indexes = [
            models.Index(fields=["partner", "indus_site_id"]),
            models.Index(fields=["partner", "site_name"]),
        ]

    def clean(self):
        super().clean()
        try:
            self.indus_site_id = validate_indus_site_id(self.indus_site_id)
        except ValidationError as exc:
            raise ValidationError({"indus_site_id": exc.messages[0]}) from exc
        try:
            self.site_name = validate_site_name(self.site_name, required=False)
        except ValidationError as exc:
            raise ValidationError({"site_name": exc.messages[0]}) from exc

    def __str__(self):
        return f"{self.indus_site_id} - {self.site_name or 'Unknown Site'}"


class DieselRouteStartPoint(models.Model):
    transporter = models.OneToOneField(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="diesel_route_start_point",
    )
    name = models.CharField(max_length=120, default="Depot")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["transporter_id"]

    def __str__(self):
        return f"{self.transporter.company_name} - {self.name}"


class DieselDailyRoutePlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    transporter = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="diesel_daily_route_plans",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="diesel_daily_route_plans",
    )
    plan_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_diesel_daily_route_plans",
        limit_choices_to={"role": "ADMIN"},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-plan_date", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "plan_date"],
                name="unique_diesel_daily_plan_per_vehicle_per_day",
            )
        ]
        indexes = [
            models.Index(fields=["vehicle", "plan_date"]),
            models.Index(fields=["transporter", "plan_date"]),
        ]

    def clean(self):
        super().clean()
        if self.vehicle_id and self.transporter_id:
            if self.vehicle.transporter_id != self.transporter_id:
                raise ValidationError({"vehicle": "Vehicle must belong to the selected transporter."})

    def __str__(self):
        return f"{self.vehicle.vehicle_number} - {self.plan_date.isoformat()}"


class DieselDailyRoutePlanStop(models.Model):
    plan = models.ForeignKey(
        "diesel.DieselDailyRoutePlan",
        on_delete=models.CASCADE,
        related_name="stops",
    )
    sequence = models.PositiveIntegerField(default=0)
    tower_site = models.ForeignKey(
        "diesel.IndusTowerSite",
        on_delete=models.SET_NULL,
        related_name="planned_route_stops",
        null=True,
        blank=True,
    )
    indus_site_id = models.CharField(max_length=64, blank=True, default="")
    site_name = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    planned_qty = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sequence", "id"]
        indexes = [
            models.Index(fields=["plan", "sequence"]),
            models.Index(fields=["plan", "tower_site"]),
        ]

    def clean(self):
        super().clean()
        if self.tower_site_id and self.plan_id:
            if self.tower_site.partner_id != self.plan.transporter_id:
                raise ValidationError({"tower_site": "Tower site must belong to the plan transporter."})
        if self.indus_site_id:
            try:
                self.indus_site_id = validate_indus_site_id(self.indus_site_id)
            except ValidationError as exc:
                raise ValidationError({"indus_site_id": exc.messages[0]}) from exc
        if self.site_name:
            try:
                self.site_name = validate_site_name(self.site_name, required=False)
            except ValidationError as exc:
                raise ValidationError({"site_name": exc.messages[0]}) from exc

    def save(self, *args, **kwargs):
        if self.tower_site_id:
            if not self.indus_site_id:
                self.indus_site_id = self.tower_site.indus_site_id
            if not self.site_name:
                self.site_name = self.tower_site.site_name or ""
            if self.latitude is None and self.tower_site.latitude is not None:
                self.latitude = self.tower_site.latitude
            if self.longitude is None and self.tower_site.longitude is not None:
                self.longitude = self.tower_site.longitude

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def resolved_indus_site_id(self):
        if self.tower_site_id:
            return self.tower_site.indus_site_id
        return self.indus_site_id

    @property
    def resolved_site_name(self):
        if self.tower_site_id:
            return self.tower_site.site_name
        return self.site_name

    @property
    def resolved_latitude(self):
        if self.tower_site_id and self.tower_site.latitude is not None:
            return self.tower_site.latitude
        return self.latitude

    @property
    def resolved_longitude(self):
        if self.tower_site_id and self.tower_site.longitude is not None:
            return self.tower_site.longitude
        return self.longitude

    def __str__(self):
        site_label = self.resolved_indus_site_id or "Unknown"
        return f"{self.plan} - {site_label}"
