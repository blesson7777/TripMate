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
