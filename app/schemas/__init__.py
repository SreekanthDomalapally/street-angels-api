from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.common.enums import AlertStatus, AlertType, GroupMemberRole, ResponseType


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class DeviceTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: str = Field(default="unknown", max_length=32)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    phone_number: str | None
    profile_photo: str | None
    is_verified: bool
    is_admin: bool
    last_known_latitude: float | None
    last_known_longitude: float | None
    notification_preferences: dict
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    profile_photo: str | None = None
    notification_preferences: dict | None = None
    last_known_latitude: float | None = None
    last_known_longitude: float | None = None


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_temporary: bool = False
    expires_at: datetime | None = None


class GroupMemberAddRequest(BaseModel):
    user_id: UUID
    role: GroupMemberRole = GroupMemberRole.MEMBER


class GroupInviteRequest(BaseModel):
    invitee_email: EmailStr


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_temporary: bool
    expires_at: datetime | None
    created_by: UUID
    created_at: datetime


class GroupInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    group_id: UUID
    inviter_id: UUID
    invitee_email: str
    status: str
    created_at: datetime
    expires_at: datetime | None


class AlertCreateRequest(BaseModel):
    group_id: UUID
    alert_type: AlertType
    message: str | None = Field(default=None, max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class AlertResponseRequest(BaseModel):
    response_type: ResponseType
    eta_minutes: int | None = Field(default=None, ge=1, le=480)


class LocationUpdateRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=10000)


class AlertResponseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    response_type: str
    eta_minutes: int | None
    created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    group_id: UUID
    alert_type: str
    message: str | None
    latitude: float
    longitude: float
    status: AlertStatus
    created_at: datetime
    resolved_at: datetime | None
    responses: list[AlertResponseItem] = []


class DonationCheckoutRequest(BaseModel):
    amount_cents: int = Field(ge=100, le=1_000_000)
    currency: str = Field(default="usd", max_length=8)
    is_anonymous: bool = False


class DonationCheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class ErrorResponse(BaseModel):
    error: str
    code: str = "error"
    details: dict = Field(default_factory=dict)
