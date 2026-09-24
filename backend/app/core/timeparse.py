"""Resolve follow-up date/time expressions from Hindi, Hinglish and English.

Design rule (§7, §13): **never invent a date**. If an expression cannot be
resolved confidently we return ``needs_confirmation`` so the review screen asks
the user instead of silently guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Kolkata"

# Part-of-day defaults, applied only when a time is not explicitly stated.
PART_OF_DAY: dict[str, time] = {
    "morning": time(10, 0),
    "subah": time(10, 0),
    "afternoon": time(14, 0),
    "dopahar": time(14, 0),
    "evening": time(17, 30),
    "shaam": time(17, 30),
    "night": time(20, 0),
    "raat": time(20, 0),
}

WEEKDAYS: dict[str, int] = {
    "monday": 0, "somvar": 0, "somwar": 0,
    "tuesday": 1, "mangalvar": 1, "mangalwar": 1,
    "wednesday": 2, "budhvar": 2, "budhwar": 2,
    "thursday": 3, "guruvar": 3, "guruwar": 3, "brihaspativar": 3,
    "friday": 4, "shukravar": 4, "shukrawar": 4,
    "saturday": 5, "shanivar": 5, "shaniwar": 5,
    "sunday": 6, "ravivar": 6, "raviwar": 6, "itwar": 6,
}

HINDI_NUMBERS: dict[str, int] = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "dus": 10,
    "pandrah": 15, "bees": 20,
}

DEFAULT_TIME = time(11, 0)  # business-hours default when only a date is known

_TIME_RE = re.compile(
    r"\b(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?P<ap>am|pm|baje|bje)?\b", re.IGNORECASE
)
_IN_N_DAYS_RE = re.compile(
    r"\b(?:(?P<num>\d{1,3})|(?P<word>[a-z]+))\s*(?:din|days?|day)\s*"
    r"(?:baad|bad|later|after|me|mein)\b",
    re.IGNORECASE,
)
_IN_N_WEEKS_RE = re.compile(
    r"\b(?:(?P<num>\d{1,2})|(?P<word>[a-z]+))\s*(?:hafte|hafta|weeks?|week)\s*"
    r"(?:baad|bad|later|after|me|mein)\b",
    re.IGNORECASE,
)
_IN_N_HOURS_RE = re.compile(
    r"\b(?:(?P<num>\d{1,2})|(?P<word>[a-z]+))\s*(?:ghante|ghanta|hours?|hrs?)\s*"
    r"(?:baad|bad|later|after)\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(?P<y>20\d{2})-(?P<mo>\d{1,2})-(?P<d>\d{1,2})\b")
_DMY_RE = re.compile(r"\b(?P<d>\d{1,2})[/-](?P<mo>\d{1,2})(?:[/-](?P<y>\d{2,4}))?\b")

# Expressions that are deliberately un-resolvable without asking the user.
AMBIGUOUS_MARKERS = (
    "baad me", "baad mein", "later", "sometime", "kabhi", "jaldi", "soon",
    "quotation bhejne ke baad", "after sending", "after quotation", "baad m",
)


@dataclass(slots=True)
class ResolvedFollowUp:
    due_at: datetime | None
    time_known: bool
    needs_confirmation: bool
    confidence: float
    reason: str
    matched_text: str | None = None


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - unknown tz falls back to IST
        return ZoneInfo(DEFAULT_TZ)


def _word_to_int(word: str | None) -> int | None:
    if not word:
        return None
    return HINDI_NUMBERS.get(word.lower())


def _explicit_clock(lowered: str) -> time | None:
    for match in _TIME_RE.finditer(lowered):
        hour = int(match.group("h"))
        minute = int(match.group("m") or 0)
        suffix = (match.group("ap") or "").lower()
        if not suffix and match.group("m") is None:
            continue  # a bare number is not a time
        if hour > 23 or minute > 59:
            continue
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif suffix in {"baje", "bje"} and hour <= 7:
            hour += 12  # "5 baje" in a sales day means 5 PM
        return time(hour, minute)
    return None


def _extract_time(text: str) -> tuple[time | None, str | None]:
    lowered = text.lower()
    for key, value in PART_OF_DAY.items():
        if re.search(rf"\b{key}\b", lowered):
            # A part-of-day word may still be followed by an explicit clock time.
            explicit = _explicit_clock(lowered)
            return (explicit or value), key
    return _explicit_clock(lowered), None


def _combine(day: date, clock: time | None, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock or DEFAULT_TIME, tzinfo=tz)


def resolve_follow_up_datetime(
    text: str | None,
    *,
    now: datetime | None = None,
    timezone: str = DEFAULT_TZ,
    explicit_time: str | None = None,
) -> ResolvedFollowUp:
    """Best-effort resolution of a natural-language follow-up expression."""
    if not text or not text.strip():
        return ResolvedFollowUp(None, False, True, 0.0, "No follow-up expression provided.")

    tz = _tz(timezone)
    now = (now or datetime.now(tz)).astimezone(tz)
    raw = text.strip()
    lowered = raw.lower()

    clock, part_of_day = _extract_time(f"{raw} {explicit_time or ''}")

    def result(day: date, confidence: float, reason: str) -> ResolvedFollowUp:
        due = _combine(day, clock, tz)
        if due <= now:  # never schedule in the past
            due = _combine(day + timedelta(days=1), clock, tz)
        return ResolvedFollowUp(
            due_at=due,
            time_known=clock is not None,
            needs_confirmation=clock is None and part_of_day is None,
            confidence=confidence,
            reason=reason,
            matched_text=raw,
        )

    # 1. Absolute dates -------------------------------------------------
    if m := _ISO_DATE_RE.search(lowered):
        return result(date(int(m["y"]), int(m["mo"]), int(m["d"])), 0.97, "Explicit ISO date.")
    if m := _DMY_RE.search(lowered):
        year = int(m["y"] or now.year)
        year += 2000 if year < 100 else 0
        try:
            return result(date(year, int(m["mo"]), int(m["d"])), 0.92, "Explicit date.")
        except ValueError:
            pass

    # 2. Relative day words ---------------------------------------------
    if re.search(r"\b(aaj|today)\b", lowered):
        return result(now.date(), 0.95, "Today.")
    if re.search(r"\b(parso|parson|day after tomorrow)\b", lowered):
        return result(now.date() + timedelta(days=2), 0.9, "Day after tomorrow.")
    if re.search(r"\b(kal|tomorrow|tomorow)\b", lowered):
        return result(now.date() + timedelta(days=1), 0.93, "Tomorrow.")

    # 3. N days / weeks / hours later -----------------------------------
    if m := _IN_N_DAYS_RE.search(lowered):
        n = int(m["num"]) if m["num"] else _word_to_int(m["word"])
        if n:
            return result(now.date() + timedelta(days=n), 0.9, f"In {n} day(s).")
    if m := _IN_N_WEEKS_RE.search(lowered):
        n = int(m["num"]) if m["num"] else _word_to_int(m["word"])
        if n:
            return result(now.date() + timedelta(weeks=n), 0.88, f"In {n} week(s).")
    if m := _IN_N_HOURS_RE.search(lowered):
        n = int(m["num"]) if m["num"] else _word_to_int(m["word"])
        if n:
            return ResolvedFollowUp(now + timedelta(hours=n), True, False, 0.88,
                                    f"In {n} hour(s).", raw)

    # 4. Weekday names ---------------------------------------------------
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            delta = (weekday - now.weekday()) % 7
            # Naming today's weekday almost always means the *next* one.
            if delta == 0 or re.search(r"\b(next|agle|agla)\b", lowered):
                delta = delta or 7
            return result(now.date() + timedelta(days=delta), 0.91, f"Weekday: {name}.")

    # 5. Coarse ranges ----------------------------------------------------
    if re.search(r"\b(next week|agle hafte|agle week)\b", lowered):
        days_to_monday = (7 - now.weekday()) or 7
        return ResolvedFollowUp(
            _combine(now.date() + timedelta(days=days_to_monday), clock, tz),
            clock is not None,
            True,  # "next week" is a range - confirm the exact day
            0.6,
            "Next week - exact day needs confirmation.",
            raw,
        )
    if re.search(r"\b(next month|agle mahine|agle month)\b", lowered):
        return ResolvedFollowUp(
            _combine(now.date() + timedelta(days=30), clock, tz),
            clock is not None,
            True,
            0.55,
            "Next month - exact day needs confirmation.",
            raw,
        )

    # 6. Part of day only (today) ----------------------------------------
    if part_of_day and clock:
        day = now.date() if _combine(now.date(), clock, tz) > now else now.date() + timedelta(1)
        return result(day, 0.75, f"Part of day: {part_of_day}.")

    # 7. Explicitly ambiguous / event-conditional -------------------------
    if any(marker in lowered for marker in AMBIGUOUS_MARKERS):
        return ResolvedFollowUp(
            None, False, True, 0.3, "Follow-up is conditional - ask the user for a date.", raw
        )

    return ResolvedFollowUp(
        None, False, True, 0.0, "Could not resolve a date from this expression.", raw
    )
