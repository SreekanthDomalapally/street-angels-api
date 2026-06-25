"""Helpers for structured logging without clobbering LogRecord reserved fields."""

from __future__ import annotations

import logging
from typing import Any

# Keys that must never appear in logger `extra` (Python logging reserved attrs).
_RESERVED_LOG_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | frozenset(
    {"message", "asctime"}
)


def safe_extra(**fields: Any) -> dict[str, Any]:
    """Return a copy of *fields* safe to pass as logger `extra=`."""
    return {key: value for key, value in fields.items() if key not in _RESERVED_LOG_KEYS}
