import re
import math

from django.core.exceptions import ValidationError


SITE_ID_PATTERN = re.compile(r"^\d{7}$")
NUMERIC_ONLY_PATTERN = re.compile(r"^\d+$")


class SiteNameUpdateConfirmationRequired(ValidationError):
    def __init__(self, *, site_id: str, existing_name: str, submitted_name: str):
        existing_label = existing_name or "no saved site name"
        submitted_label = submitted_name or "blank"
        self.site_id = site_id
        self.existing_name = existing_name
        self.submitted_name = submitted_name
        super().__init__(
            (
                f"Site ID {site_id} is already saved as '{existing_label}'. "
                f"Confirm to update it to '{submitted_label}'."
            )
        )


def normalize_site_id(site_id: str | None) -> str:
    return (site_id or "").strip()


def normalize_site_name(site_name: str | None) -> str:
    return " ".join((site_name or "").strip().split())


def validate_indus_site_id(site_id: str | None) -> str:
    normalized = normalize_site_id(site_id)
    if not normalized:
        raise ValidationError("Site ID is required.")
    if not SITE_ID_PATTERN.fullmatch(normalized):
        raise ValidationError("Site ID must be exactly 7 digits.")
    return normalized


def validate_site_name(site_name: str | None, *, required: bool = False) -> str:
    normalized = normalize_site_name(site_name)
    if required and not normalized:
        raise ValidationError("Site Name is required.")
    if normalized and NUMERIC_ONLY_PATTERN.fullmatch(normalized):
        raise ValidationError("Site Name cannot contain only numbers.")
    return normalized


def ensure_site_name_update_confirmed(
    *,
    site_id: str,
    existing_name: str,
    submitted_name: str,
    confirmed: bool,
) -> None:
    normalized_existing = normalize_site_name(existing_name)
    normalized_submitted = normalize_site_name(submitted_name)
    if (
        normalized_submitted
        and normalized_submitted != normalized_existing
        and not confirmed
    ):
        raise SiteNameUpdateConfirmationRequired(
            site_id=site_id,
            existing_name=normalized_existing,
            submitted_name=normalized_submitted,
        )


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6371000.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c
