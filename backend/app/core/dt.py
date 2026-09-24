"""Datetime helpers.

PostgreSQL returns timezone-aware values for ``TIMESTAMPTZ`` columns, but some
drivers (and SQLite in tests) hand back naive ones. Comparing the two raises, so
every comparison against "now" goes through :func:`as_aware`.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo


def as_aware(value: datetime | None, tz: tzinfo = UTC) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=tz)


def is_past(value: datetime | None, now: datetime) -> bool:
    aware = as_aware(value, now.tzinfo or UTC)
    return aware is not None and aware < now
