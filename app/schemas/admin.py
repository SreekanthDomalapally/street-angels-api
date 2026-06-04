from pydantic import BaseModel

from app.schemas.emergency import EmergencyStatus


class AdminEmergencyResponse(BaseModel):
    id: str
    userId: str
    userName: str
    status: EmergencyStatus
    startedAt: str
    lat: float
    lng: float
    contactsCount: int


class AdminUserResponse(BaseModel):
    id: str
    name: str
    email: str
    suspended: bool
    emergencies: int


class AdminUserSuspendUpdate(BaseModel):
    suspended: bool


class AdminReportResponse(BaseModel):
    id: str
    reporter: str
    target: str
    reason: str
    createdAt: str
    status: str


class AdminReportStatusUpdate(BaseModel):
    status: str
