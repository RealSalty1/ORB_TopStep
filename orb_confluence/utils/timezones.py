"""Timezone utilities."""

from datetime import datetime, timezone

import pytz


def convert_to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC.

    Args:
        dt: Datetime object (timezone-aware or naive).

    Returns:
        UTC datetime.
    """
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return dt.astimezone(timezone.utc)


def localize_time(dt: datetime, tz_name: str) -> datetime:
    """Localize datetime to specific timezone.

    Args:
        dt: UTC datetime.
        tz_name: Timezone name (e.g., 'America/Chicago').

    Returns:
        Localized datetime.
    """
    tz = pytz.timezone(tz_name)
    return dt.astimezone(tz)
