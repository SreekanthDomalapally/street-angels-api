"""Pytest configuration — stub optional deps when missing in local dev."""

import sys
from unittest.mock import MagicMock

if "pythonjsonlogger.json" not in sys.modules:
    try:
        from pythonjsonlogger.json import JsonFormatter  # noqa: F401
    except ModuleNotFoundError:
        stub = MagicMock()
        sys.modules["pythonjsonlogger"] = stub
        sys.modules["pythonjsonlogger.json"] = stub
