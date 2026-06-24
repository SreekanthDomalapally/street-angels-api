from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.common.enums import AlertStatus, AlertType, GroupMemberRole, ResponseType, TripStatus


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
    firebase_id_token: str | None = Field(default=None, min_length=10)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_credentials(self) -> "LoginRequest":
        if self.firebase_id_token:
            return self
        if self.email and self.password:
            return self
        raise ValueError("Provide firebase_id_token or email and password")


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
    email: str | None = None
    phone_number: str | None
    phone_verified: bool = False
    account_status: str = "registered"
    profile_photo: str | None
    is_verified: bool
    is_admin: bool
    last_known_latitude: float | None
    last_known_longitude: float | None
    notification_preferences: dict
    certifications: list = Field(default_factory=list)
    languages: list = Field(default_factory=list)
    vehicle_available: bool = False
    medical_background: str | None = None
    available_for_emergencies: bool = True
    location_visibility: str = "groups"
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime | None = None


class OnboardingStatus(BaseModel):
    needs_phone_verification: bool
    needs_profile_setup: bool = False
    needs_contacts_permission: bool
    onboarding_complete: bool
    account_status: str = "registered"


class FirebaseLoginRequest(BaseModel):
    firebase_id_token: str = Field(min_length=10)


class FirebaseLoginResponse(TokenPair):
    user: UserResponse
    onboarding: OnboardingStatus


class PhoneStartRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=32)
    country_code: str | None = Field(default="IE", max_length=8)


class PhoneStartResponse(BaseModel):
    session_id: UUID
    dev_otp: str | None = Field(default=None, description="Only returned in development")


class PhoneVerifyRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=32)
    otp: str = Field(min_length=4, max_length=8)
    country_code: str | None = Field(default="IE", max_length=8)


class PhoneFirebaseVerifyRequest(BaseModel):
    firebase_id_token: str = Field(min_length=10)


class ContactMatchEntry(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)


class ContactMatchRequest(BaseModel):
    contacts: list[ContactMatchEntry] = Field(min_length=1, max_length=500)
    country_code: str | None = Field(default="IE", max_length=8)


class MatchedContactUser(BaseModel):
    user_id: UUID
    display_name: str
    email: str | None = None
    phone_last4: str
    is_trusted: bool
    contact_label: str | None = None


class UnmatchedContact(BaseModel):
    phone_last4: str
    display_name: str | None = None


class ContactMatchResponse(BaseModel):
    matched_users: list[MatchedContactUser]
    unmatched_contacts: list[UnmatchedContact]
    existing_trusted_contact_ids: list[UUID]


class TrustedContactAddRequest(BaseModel):
    contact_user_id: UUID
    display_name: str | None = Field(default=None, max_length=255)


class PhoneInviteCreateRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)
    group_id: UUID | None = None
    country_code: str | None = Field(default="IE", max_length=8)


class PhoneInviteResponse(BaseModel):
    id: UUID
    invite_code: str
    invite_url: str
    invited_phone_last4: str
    status: str
    expires_at: datetime | None


class PhoneInviteDetailResponse(BaseModel):
    invite_code: str
    inviter_name: str
    display_name: str | None
    status: str
    expires_at: datetime | None


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    profile_photo: str | None = None
    notification_preferences: dict | None = None
    last_known_latitude: float | None = None
    last_known_longitude: float | None = None
    certifications: list[str] | None = Field(default=None, max_length=50)
    languages: list[str] | None = Field(default=None, max_length=50)
    vehicle_available: bool | None = None
    medical_background: str | None = Field(default=None, max_length=1000)
    available_for_emergencies: bool | None = None
    location_visibility: str | None = None


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_temporary: bool = False
    expires_at: datetime | None = None
    priority: int = Field(default=3, ge=1, le=5)
    visibility: str = Field(default="private", max_length=32)
    emergency_types: list[AlertType] | None = None


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    visibility: str | None = Field(default=None, max_length=32)


class GroupEmergencyTypesUpdateRequest(BaseModel):
    emergency_types: list[AlertType] = Field(default_factory=list)


class GroupMemberAddRequest(BaseModel):
    user_id: UUID
    role: GroupMemberRole = GroupMemberRole.MEMBER


class GroupInviteRequest(BaseModel):
    invitee_email: EmailStr | None = None
    invitee_phone: str | None = Field(default=None, min_length=6, max_length=32)
    user_id: UUID | None = None
    country_code: str | None = Field(default="IE", max_length=8)

    @model_validator(mode="after")
    def validate_target(self) -> "GroupInviteRequest":
        if self.user_id or self.invitee_email or self.invitee_phone:
            return self
        raise ValueError("Provide user_id, invitee_email, or invitee_phone")


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_temporary: bool
    expires_at: datetime | None
    priority: int = 3
    visibility: str = "private"
    created_by: UUID
    created_at: datetime


class GroupMemberResponse(BaseModel):
    user_id: UUID
    full_name: str
    email: str | None = None
    role: str


class GroupPendingInviteResponse(BaseModel):
    id: UUID
    invitee_email: str
    invitee_phone: str | None = None
    inviter_name: str
    status: str
    created_at: datetime


class GroupDetailResponse(GroupResponse):
    member_count: int
    members: list[GroupMemberResponse]
    pending_invites: list[GroupPendingInviteResponse] = Field(default_factory=list)
    emergency_types: list[str] = Field(default_factory=list)


class GroupListItemResponse(GroupResponse):
    member_count: int
    my_role: str | None = None


class UserLookupRequest(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=100)


class UserLookupMatch(BaseModel):
    email: str
    user_id: UUID
    full_name: str


class UserLookupResponse(BaseModel):
    matches: list[UserLookupMatch]


class ContactDirectoryItem(BaseModel):
    user_id: UUID | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    group_ids: list[UUID]
    status: str = Field(description="member or invited")


class ContactDirectoryResponse(BaseModel):
    contacts: list[ContactDirectoryItem]


class ContactGroupsUpdateRequest(BaseModel):
    group_ids: list[UUID] = Field(default_factory=list)


class ContactInviteGroupsRequest(BaseModel):
    email: EmailStr | None = None
    phone_number: str | None = Field(default=None, min_length=6, max_length=32)
    country_code: str | None = Field(default="IE", max_length=8)
    group_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "ContactInviteGroupsRequest":
        if self.email or self.phone_number:
            return self
        raise ValueError("Provide email or phone_number")


class GroupInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    group_id: UUID
    inviter_id: UUID
    invitee_email: str
    status: str
    created_at: datetime
    expires_at: datetime | None


class GroupInviteListItemResponse(BaseModel):
    id: UUID
    group_id: UUID
    group_name: str
    inviter_name: str
    invitee_email: str
    invitee_phone: str | None = None
    status: str
    created_at: datetime


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
    distance_km: float | None = None
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


ALLOWED_TRIP_DURATIONS = {30, 60, 120, 240}


class TripCreateRequest(BaseModel):
    group_id: UUID
    label: str | None = Field(default=None, max_length=255)
    duration_minutes: int = Field(ge=30, le=480)
    destination_latitude: float | None = Field(default=None, ge=-90, le=90)
    destination_longitude: float | None = Field(default=None, ge=-180, le=180)
    destination_label: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=10000)


class TripOut(BaseModel):
    id: UUID
    group_id: UUID
    group_name: str | None = None
    label: str | None = None
    status: TripStatus
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    destination_label: str | None = None
    current_latitude: float | None = None
    current_longitude: float | None = None
    accuracy_meters: float | None = None
    started_at: datetime
    expires_at: datetime
    arrived_at: datetime | None = None
    ended_at: datetime | None = None
    traveler_user_id: UUID
    traveler_name: str | None = None


class ErrorResponse(BaseModel):
    error: str
    code: str = "error"
    details: dict = Field(default_factory=dict)


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    category: str
    sort_order: int


class UserSkillItem(BaseModel):
    skill_code: str
    name: str
    category: str
    level: str
    verified: bool


class UserSkillInput(BaseModel):
    skill_code: str = Field(min_length=1, max_length=64)
    level: str = Field(default="basic", max_length=32)


class UserSkillsUpdateRequest(BaseModel):
    skills: list[UserSkillInput] = Field(default_factory=list, max_length=50)
