import enum


class AlertType(str, enum.Enum):
    # Canonical vocabulary (shared 1:1 with the mobile app).
    MEDICAL = "medical"
    PERSONAL_SAFETY = "personal_safety"
    CAR_BREAKDOWN = "car_breakdown"
    NEED_PICKUP = "need_pickup"
    LOST_OR_STRANDED = "lost_or_stranded"
    CUSTOM = "custom"

    # Retired codes — accepted from historical rows only.
    GENERAL_HELP = "general_help"
    MY_NEIGHBOURHOOD = "my_neighbourhood"

    # Legacy values still accepted from older clients / historical rows.
    LEGACY_UNSAFE_SITUATION = "unsafe_situation"
    LEGACY_MEDICAL_HELP = "medical_help"
    LEGACY_PICKUP_REQUEST = "pickup_request"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class ResponseType(str, enum.Enum):
    I_CAN_HELP = "i_can_help"
    ON_MY_WAY = "on_my_way"
    CALLING_NOW = "calling_now"
    UNABLE_TO_HELP = "unable_to_help"


class GroupMemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    PHONE = "phone"


class UserAccountStatus(str, enum.Enum):
    REGISTERED = "registered"
    PROFILE_PENDING = "profile_pending"
    PROFILE_COMPLETE = "profile_complete"
    CONTACTS_PENDING = "contacts_pending"
    ACTIVE = "active"


class TripStatus(str, enum.Enum):
    ACTIVE = "active"
    ARRIVED = "arrived"
    ENDED = "ended"
    EXPIRED = "expired"
