import re

import phonenumbers


def normalize_phone_e164(phone: str, default_region: str = "IE") -> str | None:
    """Normalize a phone number to E.164. Returns None if invalid."""
    raw = phone.strip()
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region if not raw.startswith("+") else None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def sanitize_display_name(name: str | None, max_length: int = 255) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        return None
    return cleaned[:max_length]
