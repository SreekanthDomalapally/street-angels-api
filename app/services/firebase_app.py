"""Lazy Firebase Admin app initialization.

Used by Firebase ID-token verification (phone/Google login). Independent of
push delivery, which now goes through Expo's push service.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_initialized = False


def _load_credentials():
    from firebase_admin import credentials

    if settings.firebase_credentials_json:
        return credentials.Certificate(json.loads(settings.firebase_credentials_json))
    if settings.firebase_credentials_path:
        return credentials.Certificate(settings.firebase_credentials_path)
    return None


def ensure_firebase_app() -> bool:
    """Initialize the default Firebase app once. Returns True if available."""
    global _initialized
    if _initialized:
        return True
    try:
        import firebase_admin

        if not firebase_admin._apps:
            cred = _load_credentials()
            options: dict[str, Any] = {"projectId": settings.firebase_project_id}
            if cred:
                firebase_admin.initialize_app(cred, options)
            else:
                firebase_admin.initialize_app(options=options)
        _initialized = True
        return True
    except Exception as exc:
        logger.warning("firebase_init_failed", extra={"error": str(exc)})
        return False
