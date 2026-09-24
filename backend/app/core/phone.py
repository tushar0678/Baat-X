"""Phone normalisation - the second half of the customer identity key."""

from __future__ import annotations

import re

import phonenumbers

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str | None, default_region: str = "IN") -> str | None:
    """Return E.164 (e.g. +919876543210) or None when not parseable.

    Falls back to a digit heuristic for the very common Indian 10-digit case so
    that dictated numbers still de-duplicate correctly.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        parsed = phonenumbers.parse(candidate, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    digits = _DIGITS.sub("", candidate)
    if default_region == "IN":
        if len(digits) == 10 and digits[0] in "6789":
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        if len(digits) == 11 and digits.startswith("0"):
            return f"+91{digits[1:]}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def mask_phone(phone: str | None) -> str:
    """+919876543210 -> +91 XXXXX 43210 (for logs and shared UI)."""
    if not phone:
        return ""
    digits = _DIGITS.sub("", phone)
    if len(digits) < 5:
        return "X" * len(digits)
    return f"+{digits[:2]} XXXXX {digits[-5:]}"
