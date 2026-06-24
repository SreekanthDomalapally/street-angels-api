"""Geo helpers for responder distance / ETA estimation."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0
# Rough urban average speed for a coarse ETA estimate (km/h).
_AVG_SPEED_KMH = 35.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def estimate_eta_minutes(distance_km: float) -> int:
    if distance_km <= 0:
        return 1
    return max(1, round((distance_km / _AVG_SPEED_KMH) * 60))
