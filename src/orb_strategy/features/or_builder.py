"""Opening Range (OR) builder with adaptive duration and validation."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger

from ..config import ORBConfig, InstrumentConfig
from .indicators import compute_atr


class ORValidity(str, Enum):
    """OR validity status."""

    VALID = "valid"
    TOO_NARROW = "too_narrow"
    TOO_WIDE = "too_wide"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class OpeningRange:
    """Opening Range data structure.

    Represents a finalized opening range with all associated metadata.
    """

    symbol: str
    date: datetime
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    
    or_high: float
    or_low: float
    or_width: float
    
    validity: ORValidity
    invalid_reason: Optional[str]
    
    # Reference ATR for validation
    atr_value: Optional[float]
    min_width_threshold: Optional[float]
    max_width_threshold: Optional[float]
    
    # Normalized volatility for adaptive selection
    normalized_vol: Optional[float]

    @property
    def is_valid(self) -> bool:
        """Check if OR is valid."""
        return self.validity == ORValidity.VALID


class ORBuilder:
    """Builds and validates Opening Ranges with adaptive duration.

    Implements adaptive OR duration selection based on normalized volatility
    and validates OR width against ATR-based thresholds.
    """

    def __init__(
        self,
        config: ORBConfig,
        instrument: InstrumentConfig,
    ) -> None:
        """Initialize OR builder.

        Args:
            config: OR configuration.
            instrument: Instrument configuration.
        """
        self.config = config
        self.instrument = instrument

    def build_opening_ranges(
        self,
        df: pd.DataFrame,
    ) -> list[OpeningRange]:
        """Build ORs for all trading days in DataFrame.

        Args:
            df: DataFrame with minute bars (UTC indexed).

        Returns:
            List of OpeningRange objects (one per trading day).
        """
        # Group by trading day
        df = df.copy()
        df["date"] = df.index.date
        
        opening_ranges = []
        
        for date, day_df in df.groupby("date"):
            try:
                or_obj = self.build_or_for_day(day_df, date)
                if or_obj is not None:
                    opening_ranges.append(or_obj)
            except Exception as e:
                logger.error(f"Failed to build OR for {date}: {e}")
                continue

        logger.info(f"Built {len(opening_ranges)} opening ranges for {self.instrument.symbol}")

        return opening_ranges

    def build_or_for_day(
        self,
        day_df: pd.DataFrame,
        date: datetime.date,
    ) -> Optional[OpeningRange]:
        """Build OR for a single trading day.

        Args:
            day_df: DataFrame with bars for the trading day.
            date: Trading date.

        Returns:
            OpeningRange object or None if insufficient data.
        """
        if day_df.empty:
            logger.debug(f"No data for {date}")
            return None

        # Determine OR duration
        if self.config.adaptive:
            or_duration = self._select_adaptive_duration(day_df)
            normalized_vol = self._compute_normalized_vol(day_df)
        else:
            or_duration = self.config.base_minutes
            normalized_vol = None

        # Get OR window
        session_start = day_df.index[0]
        or_end = session_start + timedelta(minutes=or_duration)

        or_bars = day_df[day_df.index < or_end]

        if len(or_bars) < or_duration * 0.8:  # Require 80% of expected bars
            logger.warning(
                f"Insufficient OR bars for {date}: "
                f"got {len(or_bars)}, expected ~{or_duration}"
            )
            return OpeningRange(
                symbol=self.instrument.symbol,
                date=pd.Timestamp(date),
                start_time=session_start,
                end_time=or_end,
                duration_minutes=or_duration,
                or_high=float("nan"),
                or_low=float("nan"),
                or_width=float("nan"),
                validity=ORValidity.INSUFFICIENT_DATA,
                invalid_reason="Insufficient bars in OR window",
                atr_value=None,
                min_width_threshold=None,
                max_width_threshold=None,
                normalized_vol=normalized_vol,
            )

        # Compute OR bounds
        or_high = or_bars["high"].max()
        or_low = or_bars["low"].min()
        or_width = or_high - or_low

        # Validate OR width
        validity, invalid_reason, atr_value, min_thresh, max_thresh = self._validate_or_width(
            day_df, or_width
        )

        return OpeningRange(
            symbol=self.instrument.symbol,
            date=pd.Timestamp(date),
            start_time=session_start,
            end_time=or_end,
            duration_minutes=or_duration,
            or_high=or_high,
            or_low=or_low,
            or_width=or_width,
            validity=validity,
            invalid_reason=invalid_reason,
            atr_value=atr_value,
            min_width_threshold=min_thresh,
            max_width_threshold=max_thresh,
            normalized_vol=normalized_vol,
        )

    def _select_adaptive_duration(self, day_df: pd.DataFrame) -> int:
        """Select OR duration based on normalized volatility.

        Args:
            day_df: DataFrame with bars for the day.

        Returns:
            OR duration in minutes.
        """
        norm_vol = self._compute_normalized_vol(day_df)

        if norm_vol is None:
            logger.debug("Insufficient data for adaptive OR, using base duration")
            return self.config.base_minutes

        if norm_vol < self.config.low_norm_vol:
            return self.config.short_or_minutes
        elif norm_vol > self.config.high_norm_vol:
            return self.config.long_or_minutes
        else:
            return self.config.base_minutes

    def _compute_normalized_vol(self, day_df: pd.DataFrame) -> Optional[float]:
        """Compute normalized volatility (intraday ATR / daily ATR).

        Args:
            day_df: DataFrame with bars for context.

        Returns:
            Normalized volatility or None if insufficient data.
        """
        # Need historical context - for now, use simple proxy
        # In production, would fetch multi-day history
        
        # Compute intraday ATR on available bars
        if len(day_df) < self.config.atr_period * 2:
            return None

        intraday_atr = compute_atr(day_df, period=self.config.atr_period)
        
        # Use rolling max/min as proxy for daily range
        daily_high = day_df["high"].max()
        daily_low = day_df["low"].min()
        daily_range = daily_high - daily_low

        if daily_range == 0:
            return None

        # Use last valid ATR value
        last_atr = intraday_atr.dropna().iloc[-1] if not intraday_atr.dropna().empty else None
        
        if last_atr is None or last_atr == 0:
            return None

        # Normalized vol = intraday ATR / daily range
        norm_vol = last_atr / daily_range

        return norm_vol

    def _validate_or_width(
        self,
        day_df: pd.DataFrame,
        or_width: float,
    ) -> tuple[ORValidity, Optional[str], Optional[float], Optional[float], Optional[float]]:
        """Validate OR width against ATR thresholds.

        Args:
            day_df: DataFrame with bars for ATR computation.
            or_width: OR width to validate.

        Returns:
            Tuple of (validity, invalid_reason, atr_value, min_threshold, max_threshold).
        """
        if not self.config.enable_validity_filter:
            return ORValidity.VALID, None, None, None, None

        # Compute ATR
        if len(day_df) < self.config.atr_period:
            # Not enough data for ATR
            logger.debug("Insufficient data for ATR validation")
            return ORValidity.VALID, None, None, None, None

        atr_series = compute_atr(day_df, period=self.config.atr_period)
        atr_value = atr_series.dropna().iloc[-1] if not atr_series.dropna().empty else None

        if atr_value is None or atr_value == 0:
            logger.debug("Invalid ATR for validation")
            return ORValidity.VALID, None, None, None, None

        # Compute thresholds
        min_width = self.config.min_atr_mult * atr_value
        max_width = self.config.max_atr_mult * atr_value

        # Validate
        if or_width < min_width:
            return (
                ORValidity.TOO_NARROW,
                f"OR width {or_width:.4f} < min threshold {min_width:.4f}",
                atr_value,
                min_width,
                max_width,
            )
        elif or_width > max_width:
            return (
                ORValidity.TOO_WIDE,
                f"OR width {or_width:.4f} > max threshold {max_width:.4f}",
                atr_value,
                min_width,
                max_width,
            )
        else:
            return ORValidity.VALID, None, atr_value, min_width, max_width
