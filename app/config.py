from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Convert Vercel/Neon postgres URLs to SQLAlchemy psycopg format."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie: str = "sa_session"
    session_max_age: int = 60 * 60 * 24 * 7

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "database_url",
            "DATABASE_URL",
            "POSTGRES_URL",
            "postgres_url",
        ),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str | None:
        if not self.database_url:
            return None
        return normalize_database_url(self.database_url)

    @property
    def uses_database(self) -> bool:
        return self.sqlalchemy_url is not None


settings = Settings()
