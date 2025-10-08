"""Data normalization with session filtering."""

from datetime import time, datetime, timezone
from typing import Optional

import pandas as pd
import pytz
from loguru import logger


def normalize_bars(
    df: pd.DataFrame,
    session_start: Optional[time] = None,
    session_end: Optional[time] = None,
    timezone_name: str = "America/Chicago",
) -> pd.DataFrame:
    """Normalize bar DataFrame to standard schema with optional session filtering.

    Args:
        df: Raw bar DataFrame from any source.
        session_start: Session start time (exchange local). If provided, filters to session.
        session_end: Session end time (exchange local). If provided, filters to session.
        timezone_name: Exchange timezone for session filtering.

    Returns:
        Normalized DataFrame with standard columns, sorted, deduplicated, and optionally
        filtered to session window.

    Raises:
        ValueError: If required columns are missing.
    """
    # Ensure required columns
    required = ["timestamp_utc", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Create copy to avoid modifying original
    df = df.copy()

    # Ensure timestamp is datetime with UTC timezone
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)

    # Convert numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by timestamp
    df = df.sort_values("timestamp_utc").reset_index(drop=True)

    # Drop exact duplicates (same timestamp and values)
    df = df.drop_duplicates(subset=["timestamp_utc"], keep="first")

    # Session filtering if specified
    if session_start is not None and session_end is not None:
        df = filter_to_session(df, session_start, session_end, timezone_name)

    logger.debug(f"Normalized {len(df)} bars")

    return df


def filter_to_session(
    df: pd.DataFrame,
    session_start: time,
    session_end: time,
    timezone_name: str = "America/Chicago",
) -> pd.DataFrame:
    """Filter bars to session window (exchange local time).

    Args:
        df: DataFrame with timestamp_utc column.
        session_start: Session start time (local).
        session_end: Session end time (local).
        timezone_name: Exchange timezone.

    Returns:
        Filtered DataFrame.
    """
    if df.empty:
        return df

    # Convert UTC timestamps to exchange local time
    tz = pytz.timezone(timezone_name)
    df = df.copy()
    df["local_time"] = df["timestamp_utc"].dt.tz_convert(tz)

    # Extract time component
    df["time_only"] = df["local_time"].dt.time

    # Filter to session window
    mask = (df["time_only"] >= session_start) & (df["time_only"] < session_end)
    df_filtered = df[mask].copy()

    # Drop temporary columns
    df_filtered = df_filtered.drop(columns=["local_time", "time_only"])

    logger.debug(
        f"Filtered to session {session_start}-{session_end} {timezone_name}: "
        f"{len(df_filtered)}/{len(df)} bars"
    )

    return df_filtered