"""Single source of truth for emergency-type metadata (Phase 0).

In Phase 1 this seeds the ``emergency_types`` table. For now it powers the
``GET /emergency-types`` endpoint, notification copy, and severity snapshots.
``severity``: 1 = critical .. 5 = low.
"""

from __future__ import annotations

from app.common.enums import AlertType


class EmergencyTypeMeta:
    __slots__ = ("code", "name", "icon", "description", "severity", "default_radius_km", "sort_order")

    def __init__(
        self,
        code: str,
        name: str,
        icon: str,
        description: str,
        severity: int,
        default_radius_km: float,
        sort_order: int,
    ) -> None:
        self.code = code
        self.name = name
        self.icon = icon
        self.description = description
        self.severity = severity
        self.default_radius_km = default_radius_km
        self.sort_order = sort_order


EMERGENCY_TYPES: list[EmergencyTypeMeta] = [
    EmergencyTypeMeta(
        AlertType.MEDICAL.value,
        "Medical Help",
        "medkit",
        "Injury, illness, or other medical emergency.",
        severity=1,
        default_radius_km=10,
        sort_order=10,
    ),
    EmergencyTypeMeta(
        AlertType.PERSONAL_SAFETY.value,
        "Personal Safety",
        "shield",
        "Feeling unsafe, threatened, or harassed.",
        severity=1,
        default_radius_km=5,
        sort_order=20,
    ),
    EmergencyTypeMeta(
        AlertType.CAR_BREAKDOWN.value,
        "Car Breakdown",
        "car",
        "Vehicle trouble or roadside assistance needed.",
        severity=3,
        default_radius_km=15,
        sort_order=30,
    ),
    EmergencyTypeMeta(
        AlertType.NEED_PICKUP.value,
        "Need Pickup",
        "hand-left",
        "Need a ride or to be collected from a location.",
        severity=3,
        default_radius_km=15,
        sort_order=40,
    ),
    EmergencyTypeMeta(
        AlertType.LOST_OR_STRANDED.value,
        "Lost or Stranded",
        "compass",
        "Lost, stranded, or unable to get home safely.",
        severity=2,
        default_radius_km=20,
        sort_order=50,
    ),
    EmergencyTypeMeta(
        AlertType.GENERAL_HELP.value,
        "General Help",
        "help-buoy",
        "Non-critical help from your trusted circle.",
        severity=4,
        default_radius_km=10,
        sort_order=60,
    ),
    EmergencyTypeMeta(
        AlertType.CUSTOM.value,
        "Custom",
        "ellipsis-horizontal",
        "Describe your situation in your own words.",
        severity=3,
        default_radius_km=10,
        sort_order=70,
    ),
]

# Map legacy stored values to the canonical code so old data displays correctly.
LEGACY_ALERT_TYPE_ALIASES: dict[str, str] = {
    AlertType.LEGACY_UNSAFE_SITUATION.value: AlertType.PERSONAL_SAFETY.value,
    AlertType.LEGACY_MEDICAL_HELP.value: AlertType.MEDICAL.value,
    AlertType.LEGACY_PICKUP_REQUEST.value: AlertType.NEED_PICKUP.value,
}

_BY_CODE: dict[str, EmergencyTypeMeta] = {meta.code: meta for meta in EMERGENCY_TYPES}


def canonical_code(value: str) -> str:
    return LEGACY_ALERT_TYPE_ALIASES.get(value, value)


def get_meta(value: str) -> EmergencyTypeMeta | None:
    return _BY_CODE.get(canonical_code(value))


def label_for(value: str) -> str:
    meta = get_meta(value)
    return meta.name if meta else "SOS"


def severity_for(value: str) -> int:
    meta = get_meta(value)
    return meta.severity if meta else 3
