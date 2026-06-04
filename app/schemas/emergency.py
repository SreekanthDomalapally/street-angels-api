from typing import Literal

from pydantic import BaseModel

EmergencyStatus = Literal["active", "resolved", "cancelled"]


class EmergencyResponse(BaseModel):
    id: str
    userId: str
    status: EmergencyStatus
    startedAt: str
    lat: float
    lng: float


class ActiveEmergencyResponse(BaseModel):
    emergency: EmergencyResponse | None


class EmergencyUpdate(BaseModel):
    status: EmergencyStatus | None = None
