"""Opening Range (OR) calculation with adaptive duration and validation.

Supports:
- Fixed or adaptive OR duration based on normalized volatility
- Real-time bar-by-bar OR construction
- Width validation against ATR multiples
- State tracking with finalization
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
from loguru import logger


@dataclass
class ORState:
    """Opening Range state snapshot."""

    start_ts: datetime
    end_ts: datetime
    high: float
    low: float
    width: float
    finalized: bool
    valid: bool
    invalid_reason: Optional[str] = None

    @property
    def midpoint(self) -> float:
        """Calculate OR midpoint."""
        return (self.high + self.low) / 2.0

    def __repr__(self) -> str:
        """String representation."""
        status = "✓" if self.valid else "✗"
        return (
            f"ORState({status} {self.start_ts.time()}-{self.end_ts.time()}: "
            f"H={self.high:.2f} L={self.low:.2f} W={self.width:.2f})"
        )


class OpeningRangeBuilder:
    """Real-time Opening Range builder with adaptive duration.

    Accumulates bars until OR duration is complete, then finalizes.
    Supports adaptive OR length based on normalized volatility.

    Example:
        >>> builder = OpeningRangeBuilder(
        ...     start_ts=datetime(2024, 1, 2, 14, 30),
        ...     duration_minutes=15,
        ...     adaptive=False
        ... )
        >>> for bar in bars:
        ...     builder.update(bar)
        ...     if builder.finalize_if_due(bar['timestamp_utc']):
        ...         or_state = builder.state()
        ...         print(or_state)
    """

    def __init__(
        self,
        start_ts: datetime,
        duration_minutes: int = 15,
        adaptive: bool = False,
        intraday_atr: Optional[float] = None,
        daily_atr: Optional[float] = None,
        low_norm_vol: float = 0.35,
        high_norm_vol: float = 0.85,
        short_or_minutes: int = 10,
        long_or_minutes: int = 30,
    ) -> None:
        """Initialize Opening Range builder.

        Args:
            start_ts: Session start timestamp (OR begins here).
            duration_minutes: Base OR duration in minutes.
            adaptive: Use adaptive OR duration based on volatility.
            intraday_atr: Intraday ATR for adaptive calculation.
            daily_atr: Daily ATR for adaptive calculation.
            low_norm_vol: Normalized vol threshold for short OR.
            high_norm_vol: Normalized vol threshold for long OR.
            short_or_minutes: Short OR duration (low volatility).
            long_or_minutes: Long OR duration (high volatility).
        """
        self.start_ts = start_ts
        self.adaptive = adaptive
        self.low_norm_vol = low_norm_vol
        self.high_norm_vol = high_norm_vol
        self.short_or_minutes = short_or_minutes
        self.long_or_minutes = long_or_minutes

        # Determine actual OR duration
        if adaptive and intraday_atr is not None and daily_atr is not None:
            normalized_vol = intraday_atr / daily_atr if daily_atr > 0 else 1.0
            self.duration_minutes = choose_or_length(
                normalized_vol=normalized_vol,
                low_th=low_norm_vol,
                high_th=high_norm_vol,
                short_len=short_or_minutes,
                base_len=duration_minutes,
                long_len=long_or_minutes,
            )
            logger.debug(
                f"Adaptive OR: normalized_vol={normalized_vol:.3f} → {self.duration_minutes}min"
            )
        else:
            self.duration_minutes = duration_minutes

        self.end_ts = start_ts + timedelta(minutes=self.duration_minutes)

        # State tracking
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._bar_count: int = 0
        self._finalized: bool = False
        self._valid: bool = True
        self._invalid_reason: Optional[str] = None

    def update(self, bar: pd.Series) -> None:
        """Update OR with new bar.

        Args:
            bar: Bar with 'high', 'low', 'timestamp_utc' fields.

        Raises:
            ValueError: If OR is already finalized.
        """
        if self._finalized:
            raise ValueError("Cannot update finalized OR")

        bar_ts = bar["timestamp_utc"]

        # Ignore bars outside OR window
        if bar_ts < self.start_ts or bar_ts >= self.end_ts:
            return

        # Update high/low
        if self._high is None:
            self._high = bar["high"]
            self._low = bar["low"]
        else:
            self._high = max(self._high, bar["high"])
            self._low = min(self._low, bar["low"])

        self._bar_count += 1

    def finalize_if_due(self, current_ts: datetime) -> bool:
        """Check if OR should be finalized based on timestamp.

        Args:
            current_ts: Current timestamp.

        Returns:
            True if OR was finalized (first time), False otherwise.
        """
        if self._finalized:
            return False

        if current_ts >= self.end_ts:
            self._finalize()
            return True

        return False

    def _finalize(self) -> None:
        """Finalize OR (internal method)."""
        if self._finalized:
            return

        # Check if we have data
        if self._high is None or self._low is None:
            self._valid = False
            self._invalid_reason = "No bars in OR window"
            # Set dummy values
            self._high = 0.0
            self._low = 0.0

        self._finalized = True
        logger.debug(
            f"Finalized OR: {self.start_ts.time()}-{self.end_ts.time()} "
            f"H={self._high:.2f} L={self._low:.2f} ({self._bar_count} bars)"
        )

    def state(self) -> ORState:
        """Get current OR state snapshot.

        Returns:
            ORState dataclass with current OR data.
        """
        high = self._high if self._high is not None else 0.0
        low = self._low if self._low is not None else 0.0
        width = high - low

        return ORState(
            start_ts=self.start_ts,
            end_ts=self.end_ts,
            high=high,
            low=low,
            width=width,
            finalized=self._finalized,
            valid=self._valid,
            invalid_reason=self._invalid_reason,
        )

    def is_finalized(self) -> bool:
        """Check if OR is finalized."""
        return self._finalized

    def is_valid(self) -> bool:
        """Check if OR is valid."""
        return self._valid and self._finalized


def choose_or_length(
    normalized_vol: float,
    low_th: float,
    high_th: float,
    short_len: int = 10,
    base_len: int = 15,
    long_len: int = 30,
) -> int:
    """Choose OR length based on normalized volatility.

    Logic:
    - If normalized_vol < low_th: Use short OR (low volatility)
    - If normalized_vol > high_th: Use long OR (high volatility)
    - Otherwise: Use base OR (medium volatility)

    Args:
        normalized_vol: Intraday ATR / Daily ATR.
        low_th: Low volatility threshold.
        high_th: High volatility threshold.
        short_len: Short OR duration (minutes).
        base_len: Base OR duration (minutes).
        long_len: Long OR duration (minutes).

    Returns:
        OR duration in minutes.

    Examples:
        >>> choose_or_length(0.2, 0.35, 0.85)  # Low vol
        10
        >>> choose_or_length(0.5, 0.35, 0.85)  # Medium vol
        15
        >>> choose_or_length(1.2, 0.35, 0.85)  # High vol
        30
    """
    if normalized_vol < low_th:
        return short_len
    elif normalized_vol > high_th:
        return long_len
    else:
        return base_len


def validate_or(
    or_state: ORState,
    atr_value: float,
    min_mult: float,
    max_mult: float,
) -> Tuple[bool, Optional[str]]:
    """Validate OR width against ATR multiples.

    Args:
        or_state: Opening Range state to validate.
        atr_value: Current ATR value (same timeframe as OR).
        min_mult: Minimum OR width as ATR multiple.
        max_mult: Maximum OR width as ATR multiple.

    Returns:
        Tuple of (is_valid, reason).
        - (True, None) if valid
        - (False, reason_string) if invalid

    Examples:
        >>> or_state = ORState(
        ...     start_ts=datetime(2024, 1, 2, 14, 30),
        ...     end_ts=datetime(2024, 1, 2, 14, 45),
        ...     high=100.5,
        ...     low=100.0,
        ...     width=0.5,
        ...     finalized=True,
        ...     valid=True
        ... )
        >>> validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)
        (True, None)
    """
    # Check if OR is already invalid
    if not or_state.valid:
        return False, or_state.invalid_reason

    # Check if finalized
    if not or_state.finalized:
        return False, "OR not finalized"

    # Check ATR
    if atr_value <= 0:
        return False, "Invalid ATR value"

    # Calculate width relative to ATR
    width_mult = or_state.width / atr_value

    # Check against thresholds
    if width_mult < min_mult:
        return False, f"OR too narrow ({width_mult:.2f}x < {min_mult}x ATR)"

    if width_mult > max_mult:
        return False, f"OR too wide ({width_mult:.2f}x > {max_mult}x ATR)"

    return True, None


def apply_buffer(
    or_high: float,
    or_low: float,
    fixed_buffer: float = 0.0,
    atr_buffer_mult: float = 0.0,
    atr_value: float = 0.0,
) -> Tuple[float, float]:
    """Apply buffer to OR high/low for breakout detection.

    Args:
        or_high: OR high price.
        or_low: OR low price.
        fixed_buffer: Fixed buffer in price units.
        atr_buffer_mult: ATR-based buffer multiplier.
        atr_value: Current ATR value.

    Returns:
        Tuple of (buffered_high, buffered_low).

    Examples:
        >>> apply_buffer(100.5, 100.0, fixed_buffer=0.05)
        (100.55, 99.95)

        >>> apply_buffer(100.5, 100.0, atr_buffer_mult=0.05, atr_value=1.0)
        (100.55, 99.95)
    """
    total_buffer = fixed_buffer + (atr_buffer_mult * atr_value)

    buffered_high = or_high + total_buffer
    buffered_low = or_low - total_buffer

    return buffered_high, buffered_low


def calculate_or_from_bars(
    df: pd.DataFrame,
    session_start: datetime,
    duration_minutes: int = 15,
) -> ORState:
    """Calculate OR from bar DataFrame (batch mode).

    Convenience function for calculating OR from historical data.

    Args:
        df: DataFrame with timestamp_utc, high, low columns.
        session_start: Session start timestamp.
        duration_minutes: OR duration in minutes.

    Returns:
        ORState with calculated OR.

    Raises:
        ValueError: If DataFrame is missing required columns.
    """
    required = ["timestamp_utc", "high", "low"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    builder = OpeningRangeBuilder(
        start_ts=session_start,
        duration_minutes=duration_minutes,
        adaptive=False,
    )

    # Feed bars
    for _, bar in df.iterrows():
        if bar["timestamp_utc"] >= builder.end_ts:
            break
        builder.update(bar)

    # Finalize
    builder._finalize()

    return builder.state()