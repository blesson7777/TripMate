import os
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def diesel_logbook_upload_to(_instance, filename):
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        extension = ".jpg"
    random_name = f"{uuid.uuid4().hex}{extension}"
    return os.path.join("uploads", "diesel_logs", random_name)


class FuelRecord(models.Model):
    class EntryType(models.TextChoices):
        VEHICLE_FILLING = "VEHICLE_FILLING", "Vehicle Fuel Filling"
        TOWER_DIESEL = "TOWER_DIESEL", "Tower Diesel Filling"

    attendance = models.ForeignKey(
        "attendance.Attendance",
        on_delete=models.SET_NULL,
        related_name="fuel_records",
        null=True,
        blank=True,
    )
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    partner = models.ForeignKey(
        "users.Transporter",
        on_delete=models.CASCADE,
        related_name="diesel_fill_logs",
        null=True,
        blank=True,
    )
    tower_site = models.ForeignKey(
        "diesel.IndusTowerSite",
        on_delete=models.SET_NULL,
        related_name="fill_logs",
        null=True,
        blank=True,
    )
    entry_type = models.CharField(
        max_length=24,
        choices=EntryType.choices,
        default=EntryType.VEHICLE_FILLING,
        db_index=True,
    )
    liters = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    meter_image = models.ImageField(upload_to="fuel/meter/", null=True, blank=True)
    bill_image = models.ImageField(upload_to="fuel/bill/", null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    indus_site_id = models.CharField(max_length=64, blank=True)
    site_name = models.CharField(max_length=255, blank=True)
    purpose = models.CharField(max_length=255, default="Diesel Filling", blank=True)
    fuel_filled = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    piu_reading = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    dg_hmr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    opening_stock = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_km = models.PositiveIntegerField(null=True, blank=True)
    end_km = models.PositiveIntegerField(null=True, blank=True)
    run_km = models.PositiveIntegerField(default=0)
    tower_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    tower_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fill_date = models.DateField(default=timezone.localdate)
    logbook_photo = models.ImageField(upload_to=diesel_logbook_upload_to, null=True, blank=True)
    ocr_raw_text = models.TextField(blank=True)
    ocr_confidence = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def clean(self):
        if self.vehicle_id and self.driver_id:
            if self.vehicle.transporter_id != self.driver.transporter_id:
                raise ValidationError(
                    "Fuel record vehicle must belong to the driver's current transporter."
                )
        if self.attendance_id:
            if self.attendance.driver_id != self.driver_id:
                raise ValidationError("Fuel record driver must match attendance driver.")
            if self.attendance.vehicle_id != self.vehicle_id:
                raise ValidationError("Fuel record vehicle must match attendance vehicle.")
        if self.partner_id and self.driver.transporter_id != self.partner_id:
            raise ValidationError("Partner must match the driver's transporter.")
        if self.entry_type == self.EntryType.TOWER_DIESEL:
            if self.start_km is None or self.end_km is None:
                raise ValidationError("Start KM and End KM are required for tower diesel logs.")
            if self.fuel_filled is None:
                raise ValidationError("Fuel filled is required for tower diesel logs.")
            if self.end_km < self.start_km:
                raise ValidationError("end_km must be greater than or equal to start_km.")
            if self.partner_id and getattr(self.partner, "diesel_readings_enabled", False):
                missing = {}
                if self.piu_reading is None:
                    missing["piu_reading"] = "PIU reading is required."
                if self.dg_hmr is None:
                    missing["dg_hmr"] = "DG HMR is required."
                if self.opening_stock is None:
                    missing["opening_stock"] = "Opening stock is required."
                if missing:
                    raise ValidationError(missing)
        else:
            if self.odometer_km is None:
                raise ValidationError("Odometer KM is required for vehicle fuel logs.")
            if not self.meter_image:
                raise ValidationError("Meter image is required for vehicle fuel logs.")
            if not self.bill_image:
                raise ValidationError("Bill image is required for vehicle fuel logs.")

    def save(self, *args, **kwargs):
        if self.partner_id is None and self.driver_id:
            self.partner_id = self.driver.transporter_id

        if self.entry_type == self.EntryType.TOWER_DIESEL:
            if self.fuel_filled is None:
                self.fuel_filled = self.liters
            if self.fuel_filled is not None:
                self.liters = self.fuel_filled
            if self.fill_date is None:
                self.fill_date = self.date or timezone.localdate()
            self.date = self.fill_date
            if self.start_km is not None and self.end_km is not None:
                self.run_km = max(self.end_km - self.start_km, 0)
                self.odometer_km = self.end_km
            else:
                self.run_km = 0
            if not (self.purpose or "").strip():
                self.purpose = "Diesel Filling"
        else:
            if self.fill_date is None:
                self.fill_date = self.date or timezone.localdate()
            self.date = self.fill_date
            if self.fuel_filled is None:
                self.fuel_filled = self.liters
            if self.start_km is not None and self.end_km is not None:
                self.run_km = max(self.end_km - self.start_km, 0)
            else:
                self.run_km = 0
            if self.end_km is not None and self.odometer_km is None:
                self.odometer_km = self.end_km

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        active_date = self.fill_date or self.date
        return f"{self.vehicle.vehicle_number} - {active_date}"

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
    def resolved_tower_latitude(self):
        if self.tower_site_id:
            return self.tower_site.latitude
        return self.tower_latitude

    @property
    def resolved_tower_longitude(self):
        if self.tower_site_id:
            return self.tower_site.longitude
        return self.tower_longitude
