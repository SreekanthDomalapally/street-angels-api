"""Config resolution tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_environment_uses_railway_name_when_explicit_unset():
    env = os.environ.copy()
    env.pop("ENVIRONMENT", None)
    env["RAILWAY_ENVIRONMENT_NAME"] = "production"
    env["JWT_SECRET_KEY"] = "x" * 32
    with patch.dict(os.environ, env, clear=True):
        settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.is_production is True


def test_explicit_environment_overrides_railway():
    with patch.dict(
        os.environ,
        {"RAILWAY_ENVIRONMENT_NAME": "production", "ENVIRONMENT": "staging"},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.environment == "staging"


def test_production_starts_without_jwt_secret():
    """Railway should boot so /health can report missing JWT instead of 502."""
    with patch.dict(
        os.environ,
        {"RAILWAY_ENVIRONMENT_NAME": "production"},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.jwt_secret_is_strong is False


def test_jwt_secret_is_strong_when_configured():
    with patch.dict(
        os.environ,
        {"JWT_SECRET_KEY": "x" * 32},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.jwt_secret_is_strong is True


def test_redis_url_reads_redis_url_env():
    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://redis.railway.internal:6379"},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.redis_url == "redis://redis.railway.internal:6379"


def test_dev_otp_enabled_on_production():
    with patch.dict(
        os.environ,
        {"RAILWAY_ENVIRONMENT_NAME": "production", "DEV_OTP_ENABLED": "true"},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.expose_dev_otp is True


def test_dev_otp_disabled_on_production_by_default():
    with patch.dict(
        os.environ,
        {"RAILWAY_ENVIRONMENT_NAME": "production"},
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.expose_dev_otp is False
