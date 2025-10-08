"""Adaptive Opening Range with comprehensive metrics tracking."""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class AdaptiveORState:
    """Complete OR state with all metrics."""
    start_ts: datetime
    end_ts: datetime
    high: float
    low: float
    width: float
    width_norm: float  # width / ATR
    width_percentile: float  # vs last 30 sessions
    center: float
    center_vs_prior_mid: float
    overlap_ratio: float
    overnight_range_util: float
    is_valid: bool
    invalid_reason: Optional[str]
    adaptive_length_used: int
    finalized: bool = False


class AdaptiveORBuilder:
    """Build opening range with adaptive duration and comprehensive metrics."""
    
    def __init__(
        self,
        instrument_config,
        atr_provider,
        prior_day_high: float,
        prior_day_low: float,
        overnight_high: float,
        overnight_low: float,
        session_start_ts: datetime
    ):
        """Initialize adaptive OR builder.
        
        Args:
            instrument_config: InstrumentConfig object
            atr_provider: Object with get_atr() method
            prior_day_high: Previous session high
            prior_day_low: Previous session low
            overnight_high: Overnight session high
            overnight_low: Overnight session low
            session_start_ts: Session start timestamp
        """
        self.config = instrument_config
        self.atr_provider = atr_provider
        self.prior_high = prior_day_high
        self.prior_low = prior_day_low
        self.overnight_high = overnight_high
        self.overnight_low = overnight_low
        self.session_start = session_start_ts
        
        # Will be determined adaptively
        self.or_length_minutes: Optional[int] = None
        self.or_end_ts: Optional[datetime] = None
        
        # Accumulate bars
        self.bars = []
        self.high = -np.inf
        self.low = np.inf
        self.finalized = False
        
        # Historical OR widths for percentile calculation
        self.historical_widths = []  # Will be populated externally
    
    def determine_adaptive_length(self, norm_vol: float) -> int:
        """Determine OR length based on normalized volatility.
        
        Args:
            norm_vol: Normalized volatility (intraday ATR / daily ATR)
        
        Returns:
            OR length in minutes
        """
        if norm_vol < self.config.or_low_vol_threshold:
            # Low vol → shorter OR
            length = self.config.or_min_minutes
        elif norm_vol > self.config.or_high_vol_threshold:
            # High vol → longer OR
            length = self.config.or_max_minutes
        else:
            # Normal → base length
            length = self.config.or_base_minutes
        
        logger.info(
            f"{self.config.symbol}: norm_vol={norm_vol:.3f} → OR length={length}m"
        )
        
        return length
    
    def start_or(self, norm_vol: float):
        """Start OR with adaptive length determination."""
        self.or_length_minutes = self.determine_adaptive_length(norm_vol)
        self.or_end_ts = self.session_start + timedelta(minutes=self.or_length_minutes)
        logger.info(
            f"{self.config.symbol}: OR window {self.session_start} → {self.or_end_ts}"
        )
    
    def update(self, bar: pd.Series):
        """Update OR with a new bar."""
        if self.finalized:
            return
        
        if self.or_end_ts is None:
            logger.warning("OR not started - call start_or() first")
            return
        
        timestamp = bar['timestamp']
        
        # Check if still within OR window
        if timestamp > self.or_end_ts:
            return  # Don't update after OR period
        
        # Update high/low
        self.high = max(self.high, bar['high'])
        self.low = min(self.low, bar['low'])
        
        # Store bar
        self.bars.append(bar)
    
    def finalize(self) -> AdaptiveORState:
        """Finalize OR and compute all metrics."""
        if self.finalized:
            raise ValueError("OR already finalized")
        
        self.finalized = True
        
        width = self.high - self.low
        center = (self.high + self.low) / 2.0
        
        # Get ATR for normalization
        atr = self.atr_provider.get_atr()
        if atr > 0:
            width_norm = width / atr
        else:
            width_norm = 0.0
            logger.warning(f"{self.config.symbol}: ATR is zero, cannot normalize width")
        
        # Width percentile (if we have history)
        if len(self.historical_widths) > 0:
            self.historical_widths.append(width_norm)
            if len(self.historical_widths) > 30:
                self.historical_widths.pop(0)
            width_percentile = (
                np.searchsorted(sorted(self.historical_widths), width_norm) /
                len(self.historical_widths) * 100.0
            )
        else:
            width_percentile = 50.0  # Default to median
        
        # Center vs prior mid
        prior_mid = (self.prior_high + self.prior_low) / 2.0
        center_vs_prior_mid = center - prior_mid
        
        # Overlap ratio (simplified: assume prior value area ≈ prior day range)
        prior_vah = self.prior_high * 0.75 + self.prior_low * 0.25  # Rough proxy
        prior_val = self.prior_high * 0.25 + self.prior_low * 0.75
        overlap_high = min(self.high, prior_vah)
        overlap_low = max(self.low, prior_val)
        overlap_len = max(0.0, overlap_high - overlap_low)
        overlap_ratio = overlap_len / width if width > 0 else 0.0
        
        # Overnight range utilization
        overnight_range = self.overnight_high - self.overnight_low
        typical_adr = self.config.typical_adr
        overnight_range_util = overnight_range / typical_adr if typical_adr > 0 else 0.0
        
        # Validity check
        is_valid, invalid_reason = self._check_validity(width, width_norm)
        
        return AdaptiveORState(
            start_ts=self.session_start,
            end_ts=self.or_end_ts,
            high=self.high,
            low=self.low,
            width=width,
            width_norm=width_norm,
            width_percentile=width_percentile,
            center=center,
            center_vs_prior_mid=center_vs_prior_mid,
            overlap_ratio=overlap_ratio,
            overnight_range_util=overnight_range_util,
            is_valid=is_valid,
            invalid_reason=invalid_reason,
            adaptive_length_used=self.or_length_minutes,
            finalized=True
        )
    
    def _check_validity(self, width: float, width_norm: float) -> Tuple[bool, Optional[str]]:
        """Check if OR is valid according to config rules."""
        # Check normalized width bounds
        if width_norm < self.config.validity_min_width_norm:
            return False, f"width_norm_too_low ({width_norm:.3f} < {self.config.validity_min_width_norm})"
        
        if width_norm > self.config.validity_max_width_norm:
            return False, f"width_norm_too_high ({width_norm:.3f} > {self.config.validity_max_width_norm})"
        
        # Check absolute width bounds
        if width < self.config.validity_min_width_points:
            return False, f"width_too_narrow ({width:.4f} < {self.config.validity_min_width_points})"
        
        if width > self.config.validity_max_width_points:
            return False, f"width_too_wide ({width:.4f} > {self.config.validity_max_width_points})"
        
        return True, None


class ATRProvider:
    """Simple ATR provider for OR normalization."""
    
    def __init__(self, period: int = 14):
        """Initialize ATR calculator."""
        self.period = period
        self.highs = []
        self.lows = []
        self.closes = []
    
    def update(self, high: float, low: float, close: float):
        """Update with new bar."""
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)
        
        # Keep only needed history
        if len(self.highs) > self.period + 1:
            self.highs.pop(0)
            self.lows.pop(0)
            self.closes.pop(0)
    
    def get_atr(self) -> float:
        """Calculate current ATR."""
        if len(self.highs) < 2:
            return 0.0
        
        trs = []
        for i in range(1, len(self.highs)):
            hl = self.highs[i] - self.lows[i]
            hc = abs(self.highs[i] - self.closes[i-1])
            lc = abs(self.lows[i] - self.closes[i-1])
            tr = max(hl, hc, lc)
            trs.append(tr)
        
        if len(trs) == 0:
            return 0.0
        
        # Simple average (could use Wilder's smoothing)
        return float(np.mean(trs[-self.period:]))
