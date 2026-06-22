import enum


class AlertType(str, enum.Enum):
    UNSAFE_SITUATION = "unsafe_situation"
    MEDICAL_HELP = "medical_help"
    CAR_BREAKDOWN = "car_breakdown"
    PICKUP_REQUEST = "pickup_request"
    CUSTOM = "custom"


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


class TripStatus(str, enum.Enum):
    ACTIVE = "active"
    ARRIVED = "arrived"
    ENDED = "ended"
    EXPIRED = "expired"
