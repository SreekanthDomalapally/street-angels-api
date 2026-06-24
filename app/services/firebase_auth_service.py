from typing import Any

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.logging import get_logger
from app.services.firebase_app import ensure_firebase_app

logger = get_logger(__name__)


def _ensure_firebase_app() -> None:
    ensure_firebase_app()


def verify_firebase_id_token(id_token: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return decoded claims."""
    _ensure_firebase_app()
    try:
        from firebase_admin import auth

        return auth.verify_id_token(id_token, check_revoked=True)
    except Exception as exc:
        logger.warning("firebase_token_verify_failed", extra={"error": str(exc)})
        raise UnauthorizedError("Invalid Firebase token") from exc
