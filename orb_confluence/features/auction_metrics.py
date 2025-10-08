"""Auction metrics for opening state classification.

Implements:
- Drive Energy: Directional momentum weighted by body-to-range ratio
- Rotations: Direction alternation count (chop indicator)
- Volume Z-score: Volume deviation from time-of-day expected
- Gap classification: FULL_UP, FULL_DOWN, PARTIAL, INSIDE
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd
from loguru import logger


class GapType(str, Enum):
    """Gap classification relative to prior session."""
    FULL_UP = "FULL_UP"  # Open above prior high
    FULL_DOWN = "FULL_DOWN"  # Open below prior low
    PARTIAL_UP = "PARTIAL_UP"  # Open in upper portion
    PARTIAL_DOWN = "PARTIAL_DOWN"  # Open in lower portion
    INSIDE = "INSIDE"  # Open within prior range
    NO_GAP = "NO_GAP"  # No gap or no prior data


@dataclass
class AuctionMetrics:
    """Auction metrics for state classification."""
    
    # Drive metrics
    drive_energy: float  # Directional momentum 0-1
    rotations: int  # Direction alternation count
    
    # Volume metrics
    volume_z: float  # Z-score vs time-of-day expected
    volume_ratio: float  # Actual / expected
    
    # Gap analysis
    gap_type: GapType
    gap_size_norm: float  # Gap size / ATR
    open_vs_prior_mid: float  # (open - prior_mid) / ATR
    
    # Overnight context
    overnight_range_pct: float  # Overnight range / ADR
    overnight_inventory_bias: float  # Direction bias -1 to +1
    
    # Microstructure
    bar_count: int
    avg_body_pct: float  # Average body as % of range
    max_wick_ratio: float  # Largest wick / body
    
    # Timestamps
    start_ts: datetime
    end_ts: datetime
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"AuctionMetrics(drive={self.drive_energy:.2f}, "
            f"rotations={self.rotations}, vol_z={self.volume_z:.2f}, "
            f"gap={self.gap_type})"
        )


class AuctionMetricsBuilder:
    """Real-time auction metrics calculator.
    
    Accumulates bars during OR period and computes auction characteristics.
    
    Example:
        >>> builder = AuctionMetricsBuilder(
        ...     start_ts=datetime(2024, 1, 2, 14, 30),
        ...     atr_14=2.5,
        ...     adr_20=5.0
        ... )
        >>> for bar in or_bars:
        ...     builder.add_bar(bar, expected_volume=1000)
        >>> metrics = builder.compute()
    """
    
    def __init__(
        self,
        start_ts: datetime,
        atr_14: float,
        adr_20: float,
        prior_high: Optional[float] = None,
        prior_low: Optional[float] = None,
        prior_close: Optional[float] = None,
        overnight_high: Optional[float] = None,
        overnight_low: Optional[float] = None,
    ) -> None:
        """Initialize auction metrics builder.
        
        Args:
            start_ts: OR start timestamp
            atr_14: 14-period ATR for normalization
            adr_20: 20-day average daily range
            prior_high: Prior session high
            prior_low: Prior session low
            prior_close: Prior session close
            overnight_high: Overnight session high
            overnight_low: Overnight session low
        """
        self.start_ts = start_ts
        self.end_ts = start_ts  # Updated as bars added
        self.atr_14 = atr_14
        self.adr_20 = adr_20
        
        # Prior session context
        self.prior_high = prior_high
        self.prior_low = prior_low
        self.prior_close = prior_close
        self.overnight_high = overnight_high
        self.overnight_low = overnight_low
        
        # Accumulated data
        self.bars: List[pd.Series] = []
        self.volumes: List[float] = []
        self.expected_volumes: List[float] = []
        self.directions: List[int] = []  # +1, -1, 0
        self.body_ratios: List[float] = []
        self.wick_ratios: List[float] = []
        
        self.open_price: Optional[float] = None
    
    def add_bar(
        self,
        bar: pd.Series,
        expected_volume: Optional[float] = None,
    ) -> None:
        """Add bar to auction accumulator.
        
        Args:
            bar: Bar with OHLCV data
            expected_volume: Expected volume for this time-of-day
        """
        self.bars.append(bar)
        self.end_ts = bar["timestamp_utc"]
        
        # Capture open price
        if self.open_price is None:
            self.open_price = bar["open"]
        
        # Volume tracking
        self.volumes.append(bar["volume"])
        if expected_volume is not None:
            self.expected_volumes.append(expected_volume)
        
        # Direction analysis
        body = bar["close"] - bar["open"]
        bar_range = bar["high"] - bar["low"]
        
        if bar_range > 0:
            body_ratio = abs(body) / bar_range
            self.body_ratios.append(body_ratio)
            
            # Wick analysis
            if body > 0:  # Bullish
                upper_wick = bar["high"] - bar["close"]
                lower_wick = bar["open"] - bar["low"]
            else:  # Bearish
                upper_wick = bar["high"] - bar["open"]
                lower_wick = bar["close"] - bar["low"]
            
            max_wick = max(upper_wick, lower_wick)
            wick_ratio = max_wick / abs(body) if abs(body) > 0 else 0.0
            self.wick_ratios.append(wick_ratio)
        else:
            self.body_ratios.append(0.0)
            self.wick_ratios.append(0.0)
        
        # Direction
        if body > 0:
            self.directions.append(1)
        elif body < 0:
            self.directions.append(-1)
        else:
            self.directions.append(0)
    
    def compute(self) -> AuctionMetrics:
        """Compute final auction metrics.
        
        Returns:
            AuctionMetrics with all computed values
        """
        if not self.bars:
            raise ValueError("No bars added to compute metrics")
        
        # Drive energy
        drive_energy = self._compute_drive_energy()
        
        # Rotations
        rotations = self._compute_rotations()
        
        # Volume metrics
        volume_z, volume_ratio = self._compute_volume_metrics()
        
        # Gap classification
        gap_type, gap_size_norm = self._compute_gap_metrics()
        
        # Open vs prior mid
        open_vs_prior_mid = self._compute_open_vs_prior_mid()
        
        # Overnight metrics
        overnight_range_pct, overnight_bias = self._compute_overnight_metrics()
        
        # Microstructure
        avg_body_pct = np.mean(self.body_ratios) if self.body_ratios else 0.0
        max_wick_ratio = max(self.wick_ratios) if self.wick_ratios else 0.0
        
        return AuctionMetrics(
            drive_energy=drive_energy,
            rotations=rotations,
            volume_z=volume_z,
            volume_ratio=volume_ratio,
            gap_type=gap_type,
            gap_size_norm=gap_size_norm,
            open_vs_prior_mid=open_vs_prior_mid,
            overnight_range_pct=overnight_range_pct,
            overnight_inventory_bias=overnight_bias,
            bar_count=len(self.bars),
            avg_body_pct=avg_body_pct,
            max_wick_ratio=max_wick_ratio,
            start_ts=self.start_ts,
            end_ts=self.end_ts,
        )
    
    def _compute_drive_energy(self) -> float:
        """Compute directional drive energy.
        
        Logic: Sum of (signed_body * body_ratio) / OR_width
        Higher values = strong directional momentum
        
        Returns:
            Drive energy 0-1+ (can exceed 1 for strong drives)
        """
        if not self.bars:
            return 0.0
        
        # Get OR width
        or_high = max(bar["high"] for bar in self.bars)
        or_low = min(bar["low"] for bar in self.bars)
        or_width = or_high - or_low
        
        if or_width <= 0:
            return 0.0
        
        # Weighted directional sum
        weighted_sum = 0.0
        for bar, body_ratio in zip(self.bars, self.body_ratios):
            body = bar["close"] - bar["open"]
            weighted_sum += body * body_ratio
        
        # Normalize by OR width (absolute value for magnitude)
        drive_energy = abs(weighted_sum) / or_width
        
        return min(drive_energy, 1.0)  # Cap at 1.0
    
    def _compute_rotations(self) -> int:
        """Count direction alternations.
        
        Returns:
            Number of direction changes (0-1-0 = 2 rotations)
        """
        if len(self.directions) < 2:
            return 0
        
        rotations = 0
        prev_dir = self.directions[0]
        
        for current_dir in self.directions[1:]:
            if current_dir != 0 and prev_dir != 0 and current_dir != prev_dir:
                rotations += 1
            if current_dir != 0:
                prev_dir = current_dir
        
        return rotations
    
    def _compute_volume_metrics(self) -> tuple[float, float]:
        """Compute volume Z-score and ratio.
        
        Returns:
            Tuple of (volume_z, volume_ratio)
        """
        if not self.volumes or not self.expected_volumes:
            return 0.0, 1.0
        
        total_volume = sum(self.volumes)
        total_expected = sum(self.expected_volumes)
        
        if total_expected <= 0:
            return 0.0, 1.0
        
        volume_ratio = total_volume / total_expected
        
        # Z-score (assuming expected is mean, std = 0.3 * mean as default)
        std_estimate = 0.3 * total_expected
        volume_z = (total_volume - total_expected) / std_estimate if std_estimate > 0 else 0.0
        
        return volume_z, volume_ratio
    
    def _compute_gap_metrics(self) -> tuple[GapType, float]:
        """Classify gap type and size.
        
        Returns:
            Tuple of (GapType, gap_size_norm)
        """
        if (
            self.open_price is None
            or self.prior_high is None
            or self.prior_low is None
        ):
            return GapType.NO_GAP, 0.0
        
        # Gap size
        if self.open_price > self.prior_high:
            gap_type = GapType.FULL_UP
            gap_size = self.open_price - self.prior_high
        elif self.open_price < self.prior_low:
            gap_type = GapType.FULL_DOWN
            gap_size = self.prior_low - self.open_price
        else:
            # Inside prior range
            prior_mid = (self.prior_high + self.prior_low) / 2.0
            if self.open_price > prior_mid:
                gap_type = GapType.PARTIAL_UP
            elif self.open_price < prior_mid:
                gap_type = GapType.PARTIAL_DOWN
            else:
                gap_type = GapType.INSIDE
            gap_size = 0.0
        
        # Normalize by ATR
        gap_size_norm = gap_size / self.atr_14 if self.atr_14 > 0 else 0.0
        
        return gap_type, gap_size_norm
    
    def _compute_open_vs_prior_mid(self) -> float:
        """Compute open deviation from prior mid.
        
        Returns:
            (open - prior_mid) / ATR (negative = opened below)
        """
        if (
            self.open_price is None
            or self.prior_high is None
            or self.prior_low is None
            or self.atr_14 <= 0
        ):
            return 0.0
        
        prior_mid = (self.prior_high + self.prior_low) / 2.0
        deviation = (self.open_price - prior_mid) / self.atr_14
        
        return deviation
    
    def _compute_overnight_metrics(self) -> tuple[float, float]:
        """Compute overnight range and inventory bias.
        
        Returns:
            Tuple of (overnight_range_pct, overnight_bias)
        """
        # Overnight range as % of ADR
        if (
            self.overnight_high is not None
            and self.overnight_low is not None
            and self.adr_20 > 0
        ):
            overnight_range = self.overnight_high - self.overnight_low
            overnight_range_pct = overnight_range / self.adr_20
        else:
            overnight_range_pct = 0.0
        
        # Overnight inventory bias
        if (
            self.overnight_high is not None
            and self.overnight_low is not None
            and self.prior_close is not None
            and self.open_price is not None
        ):
            overnight_range = self.overnight_high - self.overnight_low
            if overnight_range > 0:
                # Where did price settle in overnight range relative to close?
                on_mid = (self.overnight_high + self.overnight_low) / 2.0
                overnight_bias = (on_mid - self.prior_close) / overnight_range
                overnight_bias = np.clip(overnight_bias, -1.0, 1.0)
            else:
                overnight_bias = 0.0
        else:
            overnight_bias = 0.0
        
        return overnight_range_pct, overnight_bias


def compute_auction_metrics_from_bars(
    df: pd.DataFrame,
    or_start: datetime,
    or_end: datetime,
    atr_14: float,
    adr_20: float,
    prior_high: Optional[float] = None,
    prior_low: Optional[float] = None,
    prior_close: Optional[float] = None,
) -> AuctionMetrics:
    """Compute auction metrics from bar DataFrame (batch mode).
    
    Args:
        df: DataFrame with OHLCV data
        or_start: OR start timestamp
        or_end: OR end timestamp
        atr_14: 14-period ATR
        adr_20: 20-day ADR
        prior_high: Prior session high
        prior_low: Prior session low
        prior_close: Prior session close
        
    Returns:
        AuctionMetrics computed from OR bars
    """
    # Filter to OR window
    or_bars = df[
        (df["timestamp_utc"] >= or_start) & (df["timestamp_utc"] < or_end)
    ].copy()
    
    if or_bars.empty:
        raise ValueError("No bars in OR window")
    
    builder = AuctionMetricsBuilder(
        start_ts=or_start,
        atr_14=atr_14,
        adr_20=adr_20,
        prior_high=prior_high,
        prior_low=prior_low,
        prior_close=prior_close,
    )
    
    for _, bar in or_bars.iterrows():
        builder.add_bar(bar)
    
    return builder.compute()

