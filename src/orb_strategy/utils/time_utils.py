"""Time and timezone utility functions."""

from datetime import datetime, timezone as dt_timezone

import pandas as pd
import pytz


def ensure_utc(dt: datetime | pd.Timestamp) -> datetime | pd.Timestamp:
    """Ensure datetime is in UTC timezone.

    Args:
        dt: Input datetime or Timestamp.

    Returns:
        Datetime/Timestamp converted to UTC.

    Raises:
        ValueError: If datetime is naive (no timezone info).
    """
    if isinstance(dt, pd.Timestamp):
        if dt.tz is None:
            raise ValueError("Timestamp must be timezone-aware")
        return dt.tz_convert("UTC")
    
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(dt_timezone.utc)


def normalize_timezone(dt: datetime, target_tz: str) -> datetime:
    """Convert datetime to target timezone.

    Args:
        dt: Input timezone-aware datetime.
        target_tz: Target timezone name (e.g., 'America/Chicago').

    Returns:
        Datetime in target timezone.

    Raises:
        ValueError: If datetime is naive.
    """
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    
    tz = pytz.timezone(target_tz)
    return dt.astimezone(tz)
