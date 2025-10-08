"""Dual-layer Opening Range system with micro and primary OR.

Implements the OR 2.0 specification:
- Micro OR: Fixed 5-7 minutes for early state detection
- Primary OR: Adaptive 10-20 minutes based on normalized volatility
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
from loguru import logger


@dataclass
class DualORState:
    """Dual-layer OR state with micro and primary ranges."""
    
    # Micro OR (5-7 min)
    micro_start_ts: datetime
    micro_end_ts: datetime
    micro_high: float
    micro_low: float
    micro_width: float
    micro_finalized: bool
    
    # Primary OR (10-20 min adaptive)
    primary_start_ts: datetime
    primary_end_ts: datetime
    primary_high: float
    primary_low: float
    primary_width: float
    primary_finalized: bool
    primary_duration_used: int  # Actual adaptive duration
    
    # Normalization
    micro_width_norm: Optional[float] = None  # width / ATR
    primary_width_norm: Optional[float] = None
    
    # Validation
    micro_valid: bool = True
    primary_valid: bool = True
    invalid_reason: Optional[str] = None
    
    @property
    def micro_midpoint(self) -> float:
        """Micro OR midpoint."""
        return (self.micro_high + self.micro_low) / 2.0
    
    @property
    def primary_midpoint(self) -> float:
        """Primary OR midpoint."""
        return (self.primary_high + self.primary_low) / 2.0
    
    @property
    def width_ratio(self) -> float:
        """Ratio of primary to micro width (expansion indicator)."""
        if self.micro_width > 0:
            return self.primary_width / self.micro_width
        return 1.0
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DualOR(Micro: {self.micro_width:.2f}, "
            f"Primary: {self.primary_width:.2f}, "
            f"Ratio: {self.width_ratio:.2f})"
        )


class DualORBuilder:
    """Real-time dual-layer OR builder.
    
    Manages two OR layers simultaneously:
    1. Micro OR: Fixed short duration for early signal detection
    2. Primary OR: Adaptive duration based on volatility regime
    
    Example:
        >>> builder = DualORBuilder(
        ...     start_ts=datetime(2024, 1, 2, 14, 30),
        ...     micro_minutes=5,
        ...     primary_base_minutes=15,
        ...     atr_14=2.5,
        ...     atr_60=3.0
        ... )
        >>> for bar in bars:
        ...     builder.update(bar)
        ...     if builder.primary_finalized:
        ...         state = builder.state()
    """
    
    def __init__(
        self,
        start_ts: datetime,
        micro_minutes: int = 5,
        primary_base_minutes: int = 15,
        primary_min_minutes: int = 10,
        primary_max_minutes: int = 20,
        atr_14: Optional[float] = None,
        atr_60: Optional[float] = None,
        low_vol_threshold: float = 0.35,
        high_vol_threshold: float = 0.85,
    ) -> None:
        """Initialize dual OR builder.
        
        Args:
            start_ts: Session start timestamp
            micro_minutes: Micro OR duration (fixed)
            primary_base_minutes: Primary OR base duration
            primary_min_minutes: Primary OR min duration (low vol)
            primary_max_minutes: Primary OR max duration (high vol)
            atr_14: 14-period ATR for normalization
            atr_60: 60-period ATR for regime detection
            low_vol_threshold: Normalized vol threshold for short OR
            high_vol_threshold: Normalized vol threshold for long OR
        """
        self.start_ts = start_ts
        self.micro_minutes = micro_minutes
        self.atr_14 = atr_14
        self.atr_60 = atr_60
        
        # Micro OR window
        self.micro_end_ts = start_ts + timedelta(minutes=micro_minutes)
        
        # Primary OR adaptive duration
        if atr_14 is not None and atr_60 is not None and atr_60 > 0:
            normalized_vol = atr_14 / atr_60
            self.primary_duration = self._choose_primary_duration(
                normalized_vol=normalized_vol,
                low_th=low_vol_threshold,
                high_th=high_vol_threshold,
                min_len=primary_min_minutes,
                base_len=primary_base_minutes,
                max_len=primary_max_minutes,
            )
            logger.debug(
                f"Adaptive primary OR: norm_vol={normalized_vol:.3f} → {self.primary_duration}min"
            )
        else:
            self.primary_duration = primary_base_minutes
        
        self.primary_end_ts = start_ts + timedelta(minutes=self.primary_duration)
        
        # State tracking
        self._micro_high: Optional[float] = None
        self._micro_low: Optional[float] = None
        self._micro_bar_count: int = 0
        self._micro_finalized: bool = False
        
        self._primary_high: Optional[float] = None
        self._primary_low: Optional[float] = None
        self._primary_bar_count: int = 0
        self._primary_finalized: bool = False
        
        self._micro_valid: bool = True
        self._primary_valid: bool = True
        self._invalid_reason: Optional[str] = None
    
    def _choose_primary_duration(
        self,
        normalized_vol: float,
        low_th: float,
        high_th: float,
        min_len: int,
        base_len: int,
        max_len: int,
    ) -> int:
        """Choose primary OR duration based on normalized volatility.
        
        Args:
            normalized_vol: ATR_14 / ATR_60
            low_th: Low volatility threshold
            high_th: High volatility threshold
            min_len: Min duration (low vol)
            base_len: Base duration (normal vol)
            max_len: Max duration (high vol)
            
        Returns:
            OR duration in minutes
        """
        if normalized_vol < low_th:
            return min_len
        elif normalized_vol > high_th:
            return max_len
        else:
            return base_len
    
    def update(self, bar: pd.Series) -> None:
        """Update both OR layers with new bar.
        
        Args:
            bar: Bar with 'high', 'low', 'timestamp_utc' fields
        """
        bar_ts = bar["timestamp_utc"]
        
        # Update micro OR (if not finalized)
        if not self._micro_finalized and self.start_ts <= bar_ts < self.micro_end_ts:
            if self._micro_high is None:
                self._micro_high = bar["high"]
                self._micro_low = bar["low"]
            else:
                self._micro_high = max(self._micro_high, bar["high"])
                self._micro_low = min(self._micro_low, bar["low"])
            self._micro_bar_count += 1
        
        # Update primary OR (if not finalized)
        if not self._primary_finalized and self.start_ts <= bar_ts < self.primary_end_ts:
            if self._primary_high is None:
                self._primary_high = bar["high"]
                self._primary_low = bar["low"]
            else:
                self._primary_high = max(self._primary_high, bar["high"])
                self._primary_low = min(self._primary_low, bar["low"])
            self._primary_bar_count += 1
    
    def finalize_if_due(self, current_ts: datetime) -> Tuple[bool, bool]:
        """Check if either OR should be finalized.
        
        Args:
            current_ts: Current timestamp
            
        Returns:
            Tuple of (micro_finalized_now, primary_finalized_now)
        """
        micro_finalized_now = False
        primary_finalized_now = False
        
        # Check micro OR
        if not self._micro_finalized and current_ts >= self.micro_end_ts:
            self._finalize_micro()
            micro_finalized_now = True
        
        # Check primary OR
        if not self._primary_finalized and current_ts >= self.primary_end_ts:
            self._finalize_primary()
            primary_finalized_now = True
        
        return micro_finalized_now, primary_finalized_now
    
    def _finalize_micro(self) -> None:
        """Finalize micro OR."""
        if self._micro_finalized:
            return
        
        if self._micro_high is None or self._micro_low is None:
            self._micro_valid = False
            self._invalid_reason = "No bars in micro OR window"
            self._micro_high = 0.0
            self._micro_low = 0.0
        
        self._micro_finalized = True
        logger.debug(
            f"Finalized micro OR: {self.micro_minutes}min, "
            f"H={self._micro_high:.2f} L={self._micro_low:.2f}"
        )
    
    def _finalize_primary(self) -> None:
        """Finalize primary OR."""
        if self._primary_finalized:
            return
        
        if self._primary_high is None or self._primary_low is None:
            self._primary_valid = False
            self._invalid_reason = "No bars in primary OR window"
            self._primary_high = 0.0
            self._primary_low = 0.0
        
        self._primary_finalized = True
        logger.debug(
            f"Finalized primary OR: {self.primary_duration}min, "
            f"H={self._primary_high:.2f} L={self._primary_low:.2f}"
        )
    
    def state(self) -> DualORState:
        """Get current dual OR state.
        
        Returns:
            DualORState with both OR layers
        """
        micro_high = self._micro_high if self._micro_high is not None else 0.0
        micro_low = self._micro_low if self._micro_low is not None else 0.0
        micro_width = micro_high - micro_low
        
        primary_high = self._primary_high if self._primary_high is not None else 0.0
        primary_low = self._primary_low if self._primary_low is not None else 0.0
        primary_width = primary_high - primary_low
        
        # Compute normalized widths
        micro_width_norm = None
        primary_width_norm = None
        if self.atr_14 is not None and self.atr_14 > 0:
            micro_width_norm = micro_width / self.atr_14
            primary_width_norm = primary_width / self.atr_14
        
        return DualORState(
            micro_start_ts=self.start_ts,
            micro_end_ts=self.micro_end_ts,
            micro_high=micro_high,
            micro_low=micro_low,
            micro_width=micro_width,
            micro_finalized=self._micro_finalized,
            primary_start_ts=self.start_ts,
            primary_end_ts=self.primary_end_ts,
            primary_high=primary_high,
            primary_low=primary_low,
            primary_width=primary_width,
            primary_finalized=self._primary_finalized,
            primary_duration_used=self.primary_duration,
            micro_width_norm=micro_width_norm,
            primary_width_norm=primary_width_norm,
            micro_valid=self._micro_valid,
            primary_valid=self._primary_valid,
            invalid_reason=self._invalid_reason,
        )
    
    @property
    def micro_finalized(self) -> bool:
        """Check if micro OR is finalized."""
        return self._micro_finalized
    
    @property
    def primary_finalized(self) -> bool:
        """Check if primary OR is finalized."""
        return self._primary_finalized
    
    @property
    def both_finalized(self) -> bool:
        """Check if both ORs are finalized."""
        return self._micro_finalized and self._primary_finalized


def calculate_dual_or_from_bars(
    df: pd.DataFrame,
    session_start: datetime,
    micro_minutes: int = 5,
    primary_minutes: int = 15,
    atr_value: Optional[float] = None,
) -> DualORState:
    """Calculate dual OR from bar DataFrame (batch mode).
    
    Args:
        df: DataFrame with timestamp_utc, high, low columns
        session_start: Session start timestamp
        micro_minutes: Micro OR duration
        primary_minutes: Primary OR duration
        atr_value: ATR for normalization
        
    Returns:
        DualORState with calculated ORs
    """
    required = ["timestamp_utc", "high", "low"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    builder = DualORBuilder(
        start_ts=session_start,
        micro_minutes=micro_minutes,
        primary_base_minutes=primary_minutes,
        atr_14=atr_value,
    )
    
    # Feed bars
    for _, bar in df.iterrows():
        if bar["timestamp_utc"] >= builder.primary_end_ts:
            break
        builder.update(bar)
        builder.finalize_if_due(bar["timestamp_utc"])
    
    # Force finalize both
    if not builder._micro_finalized:
        builder._finalize_micro()
    if not builder._primary_finalized:
        builder._finalize_primary()
    
    return builder.state()

