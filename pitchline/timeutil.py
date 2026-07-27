"""Time helpers — send windows (R4.5), follow-up spacing (R4.2), TTL freshness (R1.3).

SQLite drops tzinfo on round-trip, so anything read back from the database goes through
``ensure_utc`` before it is compared. A naive datetime compared against an aware one is a
``TypeError`` at best and a silently wrong send window at worst.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pitchline.rules import (
    ALLOWED_SEND_WEEKDAYS_ISO,
    SEND_WINDOW_END_HOUR,
    SEND_WINDOW_START_HOUR,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime; convert an aware one. ``None`` passes through."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def age_days(value: datetime | None, *, now: datetime | None = None) -> float:
    aware = ensure_utc(value)
    if aware is None:
        return float("inf")
    return ((now or utcnow()) - aware).total_seconds() / 86400.0


def resolve_timezone(name: str | None) -> ZoneInfo | None:
    """R4.5 — an unknown timezone is ``None``, which means defer, not guess."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def add_business_days(start: datetime, days: int) -> datetime:
    """R4.2 — follow-up spacing counts business days, not calendar days."""
    if days <= 0:
        return start
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.isoweekday() <= 5:
            remaining -= 1
    return current


def next_send_window(
    after: datetime, tz_name: str | None, *, max_days_ahead: int = 21
) -> datetime | None:
    """The next moment inside the R4.5 window, in UTC.

    Returns ``None`` when the recipient timezone is unknown — the caller defers rather than
    guessing, because a mistimed send spends reputation for nothing.
    """
    tz = resolve_timezone(tz_name)
    if tz is None:
        return None
    cursor = ensure_utc(after) or utcnow()
    local = cursor.astimezone(tz)
    for offset in range(max_days_ahead + 1):
        day = (local + timedelta(days=offset)).date()
        candidate_local = datetime.combine(day, time(hour=SEND_WINDOW_START_HOUR), tzinfo=tz)
        if candidate_local.isoweekday() not in ALLOWED_SEND_WEEKDAYS_ISO:
            continue
        if offset == 0 and local.isoweekday() in ALLOWED_SEND_WEEKDAYS_ISO:
            # Already inside today's window: send now rather than waiting a week.
            if SEND_WINDOW_START_HOUR <= local.hour < SEND_WINDOW_END_HOUR:
                return cursor
            if local.hour < SEND_WINDOW_START_HOUR:
                return candidate_local.astimezone(timezone.utc)
            continue  # window has closed for today
        if candidate_local.astimezone(timezone.utc) > cursor:
            return candidate_local.astimezone(timezone.utc)
    return None


def today_utc() -> date:
    return utcnow().date()
