from functools import lru_cache
import logging
import os

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

UNSAFE_JWT_SECRETS = frozenset(
    {"", "change-me-in-production", "changeme", "secret", "change-me-use-openssl-rand-hex-32"}
)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "YouHoo Alert API"
    app_version: str = "1.0.0"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME"),
    )
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Use "*" on Railway for mobile + Expo web; or comma-separated origins.
    cors_origins: str = "*"
    admin_emails: str = ""

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABASE_URL",
            "DATABASE_PUBLIC_URL",
            "POSTGRES_URL",
            "database_url",
        ),
    )
    database_url_unpooled: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABASE_URL_UNPOOLED",
            "DATABASE_PUBLIC_URL",
            "POSTGRES_URL_NON_POOLING",
            "database_url_unpooled",
        ),
    )

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )

    jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    google_oauth_client_id: str | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_ID")

    firebase_project_id: str = Field(default="youhoo-alert-app", alias="FIREBASE_PROJECT_ID")
    firebase_android_package: str = Field(
        default="com.youhooalert.app", alias="FIREBASE_ANDROID_PACKAGE"
    )
    firebase_ios_bundle_id: str = Field(
        default="com.youhoolert.app", alias="FIREBASE_IOS_BUNDLE_ID"
    )
    firebase_credentials_path: str | None = Field(default=None, alias="FIREBASE_CREDENTIALS_PATH")
    firebase_credentials_json: str | None = Field(default=None, alias="FIREBASE_CREDENTIALS_JSON")

    # Push delivery via Expo's push service (relays to FCM/APNs).
    push_enabled: bool = Field(default=True, alias="PUSH_ENABLED")
    expo_access_token: str | None = Field(default=None, alias="EXPO_ACCESS_TOKEN")

    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_donation_success_url: str = "https://youhooalert.com/donate/success"
    stripe_donation_cancel_url: str = "https://youhooalert.com/donate/cancel"

    alert_rate_limit: str = "5/minute"
    auth_rate_limit: str = "10/minute"
    enable_legacy_api: bool = Field(default=False, alias="ENABLE_LEGACY_API")
    # Return OTP in API responses for Expo Go / internal testing (no SMS). Disable before public launch.
    dev_otp_enabled: bool = Field(default=False, alias="DEV_OTP_ENABLED")
    # SOS /debug routes (routing preview, test push). Off in production unless explicitly enabled.
    sos_debug_endpoints_enabled: bool = Field(default=False, alias="SOS_DEBUG_ENDPOINTS_ENABLED")
    location_min_update_seconds: float = 5.0
    location_max_accuracy_meters: float = 500.0
    sos_cooldown_seconds: int = Field(default=60, alias="SOS_COOLDOWN_SECONDS")
    recipient_cap: int = Field(default=50, alias="RECIPIENT_CAP")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, alias="TWILIO_FROM_NUMBER")

    @model_validator(mode="after")
    def warn_on_weak_production_secrets(self) -> "Settings":
        if not self.jwt_secret_is_strong:
            logger.critical(
                "JWT_SECRET_KEY is missing or too weak. "
                "Set a random 32+ character JWT_SECRET_KEY. Auth tokens are insecure until fixed."
            )
        if self.is_production and self.dev_otp_enabled:
            logger.warning(
                "DEV_OTP_ENABLED=true on production — login codes are returned in API responses. "
                "Disable before public launch."
            )
        return self

    @property
    def expose_dev_otp(self) -> bool:
        return self.environment.lower() == "development" or self.dev_otp_enabled

    @property
    def jwt_secret_is_strong(self) -> bool:
        key = self.jwt_secret_key.strip()
        return key.lower() not in UNSAFE_JWT_SECRETS and len(key) >= 32

    @model_validator(mode="before")
    @classmethod
    def resolve_environment_from_railway(cls, data: object) -> object:
        """Prefer Railway's injected env name when ENVIRONMENT is unset or left as default."""
        payload = dict(data) if isinstance(data, dict) else {}
        explicit = os.environ.get("ENVIRONMENT", "").strip()
        railway = os.environ.get("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
        current = str(payload.get("environment") or explicit or "development").strip().lower()
        if railway and (not explicit or current == "development"):
            payload["environment"] = railway
        return payload

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def sqlalchemy_url(self) -> str | None:
        if not self.database_url:
            return None
        return normalize_database_url(self.database_url)

    @property
    def sqlalchemy_migration_url(self) -> str | None:
        url = self.database_url_unpooled or self.database_url
        return normalize_database_url(url) if url else None

    @property
    def uses_database(self) -> bool:
        return self.sqlalchemy_url is not None

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def sos_debug_endpoints_available(self) -> bool:
        """Debug HTTP routes: always in non-production; in production only when flag is set."""
        return not self.is_production or self.sos_debug_endpoints_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
