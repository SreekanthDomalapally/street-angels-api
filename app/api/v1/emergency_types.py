from fastapi import APIRouter

from app.common.emergency_types import EMERGENCY_TYPES

router = APIRouter(prefix="/emergency-types", tags=["emergency-types"])


@router.get("")
async def list_emergency_types() -> list[dict]:
    """Canonical emergency-type catalog. Drives the SOS screen and routing."""
    return [
        {
            "code": meta.code,
            "name": meta.name,
            "icon": meta.icon,
            "description": meta.description,
            "severity": meta.severity,
            "default_radius_km": meta.default_radius_km,
            "sort_order": meta.sort_order,
        }
        for meta in sorted(EMERGENCY_TYPES, key=lambda m: m.sort_order)
    ]
