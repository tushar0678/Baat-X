"""Follow-up intelligence: Hindi / Hinglish / English date understanding (§13)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.timeparse import resolve_follow_up_datetime

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 21, 10, 0, tzinfo=IST)  # a Monday


@pytest.mark.parametrize(
    ("text", "days_ahead"),
    [
        ("Friday ko call karna", 4),
        ("call her on Friday", 4),
        ("kal call back kar lena", 1),
        ("tomorrow morning call", 1),
        ("2 din baad call karna", 2),
        ("10 din baad call karna", 10),
        ("parso quotation bhejna", 2),
        ("aaj shaam ko call karna", 0),
        ("Monday ko available hoga", 7),  # said on a Monday -> next Monday
        ("do din baad call karna", 2),
    ],
)
def test_resolves_common_expressions(text: str, days_ahead: int) -> None:
    resolved = resolve_follow_up_datetime(text, now=NOW, timezone="Asia/Kolkata")
    assert resolved.due_at is not None, text
    assert (resolved.due_at.date() - NOW.date()).days == days_ahead
    assert resolved.due_at > NOW


def test_evening_maps_to_business_evening() -> None:
    resolved = resolve_follow_up_datetime("shaam ko call karna", now=NOW, timezone="Asia/Kolkata")
    assert resolved.due_at.hour == 17


def test_next_week_is_a_range_and_needs_confirmation() -> None:
    resolved = resolve_follow_up_datetime("next week baat karte hain", now=NOW)
    assert resolved.needs_confirmation is True
    assert resolved.confidence < 0.9


def test_conditional_expression_is_never_invented() -> None:
    resolved = resolve_follow_up_datetime("quotation bhejne ke baad call karna", now=NOW)
    assert resolved.due_at is None
    assert resolved.needs_confirmation is True


def test_unparseable_returns_nothing() -> None:
    assert resolve_follow_up_datetime("kabhi bhi baat kar lenge", now=NOW).due_at is None


def test_explicit_clock_time_is_honoured() -> None:
    resolved = resolve_follow_up_datetime("kal 4 pm call karna", now=NOW)
    assert resolved.due_at.hour == 16
    assert resolved.time_known is True
