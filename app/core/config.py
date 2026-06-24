from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    environment: str = "development"
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

    redis_url: str = "redis://localhost:6379/0"

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
    fcm_enabled: bool = Field(default=False, alias="FCM_ENABLED")

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
    location_min_update_seconds: float = 5.0
    location_max_accuracy_meters: float = 500.0

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.is_production:
            unsafe = {"", "change-me-in-production", "changeme", "secret"}
            if self.jwt_secret_key.lower() in unsafe or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be a random string of at least 32 characters in production"
                )
        return self

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
