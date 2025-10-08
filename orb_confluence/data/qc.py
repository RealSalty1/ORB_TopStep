"""Data quality control with gap detection and OR window validation."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

import pandas as pd
from loguru import logger


@dataclass
class DayQualityReport:
    """Quality control report for a single trading day."""

    date: datetime.date
    total_bars: int
    expected_bars: int
    missing_bars: int
    duplicate_timestamps: int
    gaps: List[Tuple[datetime, datetime]]  # List of (gap_start, gap_end)
    or_window_complete: bool
    or_window_gaps: List[Tuple[datetime, datetime]]
    invalid_ohlc_count: int
    zero_volume_count: int
    passed: bool
    failure_reasons: List[str]

    def __repr__(self) -> str:
        """String representation."""
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        return (
            f"DayQualityReport({self.date}): {status}\n"
            f"  Bars: {self.total_bars}/{self.expected_bars} "
            f"(missing: {self.missing_bars})\n"
            f"  Gaps: {len(self.gaps)}, OR Window: {'✓' if self.or_window_complete else '✗'}\n"
            f"  Issues: {', '.join(self.failure_reasons) if self.failure_reasons else 'None'}"
        )


def quality_check(
    df: pd.DataFrame,
    or_duration_minutes: int = 15,
    expected_bars_per_day: int = 390,
    allow_missing_pct: float = 0.05,
) -> DayQualityReport:
    """Perform comprehensive quality checks on bar data.

    Args:
        df: DataFrame with bars for a single day (timestamp_utc indexed or column).
        or_duration_minutes: OR duration for checking completeness.
        expected_bars_per_day: Expected number of bars per trading day.
        allow_missing_pct: Allowed percentage of missing bars (0.05 = 5%).

    Returns:
        DayQualityReport with detailed quality metrics.
    """
    failure_reasons = []

    # Ensure we have a timestamp column
    if "timestamp_utc" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df = df.rename(columns={"index": "timestamp_utc"})
        else:
            raise ValueError("DataFrame must have timestamp_utc column or DatetimeIndex")

    if df.empty:
        return DayQualityReport(
            date=datetime.now().date(),
            total_bars=0,
            expected_bars=expected_bars_per_day,
            missing_bars=expected_bars_per_day,
            duplicate_timestamps=0,
            gaps=[],
            or_window_complete=False,
            or_window_gaps=[],
            invalid_ohlc_count=0,
            zero_volume_count=0,
            passed=False,
            failure_reasons=["Empty DataFrame"],
        )

    date = df["timestamp_utc"].iloc[0].date()
    total_bars = len(df)

    # Check for duplicate timestamps
    duplicate_count = df["timestamp_utc"].duplicated().sum()
    if duplicate_count > 0:
        failure_reasons.append(f"{duplicate_count} duplicate timestamps")

    # Check for gaps in minute coverage
    gaps = detect_gaps(df["timestamp_utc"])

    # Check OR window completeness (first N minutes)
    or_window_complete, or_window_gaps = check_or_window(
        df["timestamp_utc"], or_duration_minutes
    )
    if not or_window_complete:
        failure_reasons.append(f"Incomplete OR window ({len(or_window_gaps)} gaps)")

    # Check for invalid OHLC relationships
    invalid_ohlc = check_ohlc_validity(df)
    if invalid_ohlc > 0:
        failure_reasons.append(f"{invalid_ohlc} invalid OHLC bars")

    # Check for zero/negative volume
    zero_volume = (df["volume"] <= 0).sum()
    if zero_volume > 0:
        failure_reasons.append(f"{zero_volume} zero-volume bars")

    # Calculate missing bars
    missing_bars = expected_bars_per_day - total_bars

    # Overall pass/fail
    max_allowed_missing = int(expected_bars_per_day * allow_missing_pct)
    passed = (
        len(failure_reasons) == 0
        and missing_bars <= max_allowed_missing
        and or_window_complete
    )

    if missing_bars > max_allowed_missing:
        failure_reasons.append(
            f"Too many missing bars ({missing_bars} > {max_allowed_missing})"
        )

    report = DayQualityReport(
        date=date,
        total_bars=total_bars,
        expected_bars=expected_bars_per_day,
        missing_bars=max(0, missing_bars),
        duplicate_timestamps=duplicate_count,
        gaps=gaps,
        or_window_complete=or_window_complete,
        or_window_gaps=or_window_gaps,
        invalid_ohlc_count=invalid_ohlc,
        zero_volume_count=zero_volume,
        passed=passed,
        failure_reasons=failure_reasons,
    )

    logger.info(f"Quality check for {date}: {'PASSED' if passed else 'FAILED'}")
    if failure_reasons:
        logger.warning(f"  Issues: {', '.join(failure_reasons)}")

    return report


def detect_gaps(
    timestamps: pd.Series,
    expected_freq: str = "1min",
) -> List[Tuple[datetime, datetime]]:
    """Detect gaps in timestamp series.

    Args:
        timestamps: Series of timestamps (sorted).
        expected_freq: Expected frequency (e.g., '1min').

    Returns:
        List of (gap_start, gap_end) tuples.
    """
    if len(timestamps) < 2:
        return []

    gaps = []
    expected_delta = pd.Timedelta(expected_freq)

    for i in range(1, len(timestamps)):
        delta = timestamps.iloc[i] - timestamps.iloc[i - 1]
        if delta > expected_delta:
            gap_start = timestamps.iloc[i - 1]
            gap_end = timestamps.iloc[i]
            gaps.append((gap_start, gap_end))

    return gaps


def check_or_window(
    timestamps: pd.Series,
    or_duration_minutes: int,
) -> Tuple[bool, List[Tuple[datetime, datetime]]]:
    """Check if OR window has continuous minute coverage.

    Args:
        timestamps: Series of timestamps (sorted).
        or_duration_minutes: OR duration in minutes.

    Returns:
        Tuple of (is_complete, gaps_in_or_window).
    """
    if timestamps.empty:
        return False, []

    session_start = timestamps.iloc[0]
    or_end = session_start + pd.Timedelta(minutes=or_duration_minutes)

    # Filter to OR window
    or_timestamps = timestamps[timestamps < or_end]

    if len(or_timestamps) < or_duration_minutes * 0.9:  # Allow 10% tolerance
        # Not enough bars in OR window
        return False, [(session_start, or_end)]

    # Check for gaps within OR window
    or_gaps = detect_gaps(or_timestamps)

    is_complete = len(or_gaps) == 0

    return is_complete, or_gaps


def check_ohlc_validity(df: pd.DataFrame) -> int:
    """Check for invalid OHLC relationships.

    Args:
        df: DataFrame with OHLC columns.

    Returns:
        Count of invalid bars.
    """
    # Check: high >= low, high >= open, high >= close, low <= open, low <= close
    invalid = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )

    return invalid.sum()


def validate_or_window(bars_subset: pd.DataFrame, or_duration_minutes: int = 15) -> bool:
    """Validate that OR window has continuous minute coverage.
    
    This is the primary function to call before accepting an OR for trading.
    
    Args:
        bars_subset: DataFrame with bars for OR window (should be first N minutes).
        or_duration_minutes: Expected OR duration in minutes.
        
    Returns:
        True if OR window is valid (continuous minutes), False otherwise.
    """
    if bars_subset.empty:
        logger.warning("OR window validation failed: empty DataFrame")
        return False
    
    # Ensure we have timestamp column
    if "timestamp_utc" not in bars_subset.columns:
        if isinstance(bars_subset.index, pd.DatetimeIndex):
            bars_subset = bars_subset.reset_index()
            bars_subset = bars_subset.rename(columns={"index": "timestamp_utc"})
        else:
            logger.error("OR window validation failed: no timestamp column")
            return False
    
    # Check we have enough bars (allow 90% tolerance for edge cases)
    min_expected_bars = int(or_duration_minutes * 0.9)
    if len(bars_subset) < min_expected_bars:
        logger.warning(
            f"OR window validation failed: insufficient bars "
            f"({len(bars_subset)} < {min_expected_bars})"
        )
        return False
    
    # Check for gaps in minute coverage
    is_complete, gaps = check_or_window(bars_subset["timestamp_utc"], or_duration_minutes)
    
    if not is_complete:
        logger.warning(
            f"OR window validation failed: {len(gaps)} gap(s) detected in minute coverage"
        )
        for gap_start, gap_end in gaps:
            gap_minutes = (gap_end - gap_start).total_seconds() / 60
            logger.warning(f"  Gap: {gap_start} to {gap_end} ({gap_minutes:.1f} minutes)")
        return False
    
    # Check for invalid OHLC
    invalid_count = check_ohlc_validity(bars_subset)
    if invalid_count > 0:
        logger.warning(
            f"OR window validation failed: {invalid_count} invalid OHLC bar(s)"
        )
        return False
    
    logger.info(f"OR window validation passed: {len(bars_subset)} continuous bars")
    return True


def detect_outliers(
    volume_series: pd.Series,
    method: str = "iqr",
    threshold: float = 3.0
) -> List[int]:
    """Detect outlier indices in volume series.
    
    Args:
        volume_series: Series of volume values.
        method: Detection method ('iqr', 'zscore', 'mad').
        threshold: Threshold for outlier detection.
            - For 'iqr': multiple of IQR (default 3.0 = very conservative)
            - For 'zscore': z-score threshold (default 3.0)
            - For 'mad': multiple of MAD (default 3.0)
            
    Returns:
        List of indices where outliers were detected.
    """
    if volume_series.empty:
        return []
    
    outlier_indices = []
    
    if method == "iqr":
        # Interquartile Range method
        q1 = volume_series.quantile(0.25)
        q3 = volume_series.quantile(0.75)
        iqr = q3 - q1
        
        lower_bound = q1 - threshold * iqr
        upper_bound = q3 + threshold * iqr
        
        outliers = (volume_series < lower_bound) | (volume_series > upper_bound)
        outlier_indices = volume_series[outliers].index.tolist()
        
    elif method == "zscore":
        # Z-score method
        mean = volume_series.mean()
        std = volume_series.std()
        
        if std > 0:
            z_scores = (volume_series - mean).abs() / std
            outliers = z_scores > threshold
            outlier_indices = volume_series[outliers].index.tolist()
    
    elif method == "mad":
        # Median Absolute Deviation method
        median = volume_series.median()
        mad = (volume_series - median).abs().median()
        
        if mad > 0:
            modified_z_scores = 0.6745 * (volume_series - median).abs() / mad
            outliers = modified_z_scores > threshold
            outlier_indices = volume_series[outliers].index.tolist()
    
    else:
        raise ValueError(f"Unknown method: {method}. Use 'iqr', 'zscore', or 'mad'.")
    
    if outlier_indices:
        logger.info(f"Detected {len(outlier_indices)} volume outlier(s) using {method} method")
    
    return outlier_indices