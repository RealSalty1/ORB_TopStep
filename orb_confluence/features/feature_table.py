"""Feature table schema builder for ORB 2.0.

Unified feature matrix with all factors for:
- Auction state classification
- Signal generation
- Probability modeling
- Context exclusion
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional

import pandas as pd
from loguru import logger

from .or_layers import DualORState
from .auction_metrics import AuctionMetrics, GapType


@dataclass
class FeatureRow:
    """Single row in feature table (bar-level features)."""
    
    # Timestamp & identification
    ts: datetime
    instrument: str
    session_date: str
    
    # OHLCV
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    # ATR references
    atr_14: float
    atr_60: float
    adr_20: float  # Average daily range
    
    # Returns
    ret_1m: float  # Log return
    
    # OR Layers
    or_micro_high: Optional[float] = None
    or_micro_low: Optional[float] = None
    or_micro_width: Optional[float] = None
    or_micro_width_norm: Optional[float] = None
    or_micro_finalized: bool = False
    
    or_primary_high: Optional[float] = None
    or_primary_low: Optional[float] = None
    or_primary_width: Optional[float] = None
    or_primary_width_norm: Optional[float] = None
    or_primary_duration_used: Optional[int] = None
    or_primary_finalized: bool = False
    
    # Auction Metrics (populated after OR finalized)
    drive_energy: Optional[float] = None
    rotations: Optional[int] = None
    vol_z: Optional[float] = None
    gap_type: Optional[str] = None
    gap_size_norm: Optional[float] = None
    overnight_range_pct: Optional[float] = None
    
    # VWAP
    vwap: Optional[float] = None
    vwap_dev_norm: Optional[float] = None  # (price - vwap) / ATR
    
    # Volume Profile Proxy
    value_area_high: Optional[float] = None
    value_area_low: Optional[float] = None
    point_of_control: Optional[float] = None
    
    # Relative Volume
    volume_ratio: Optional[float] = None  # vs time-of-day expected
    volume_spike: bool = False
    
    # ADX
    adx: Optional[float] = None
    
    # Cross-instrument (for ES/NQ)
    es_nq_spread: Optional[float] = None
    
    # State classification (populated after auction analysis)
    auction_state: Optional[str] = None
    auction_state_confidence: Optional[float] = None
    regime_vol: Optional[str] = None  # LOW, NORMAL, EXPANSION
    
    # Context exclusion
    context_excluded: bool = False
    context_exclusion_reason: Optional[str] = None
    
    # Probability model (populated for signals)
    p_extension: Optional[float] = None
    
    # Price action
    distance_from_or_high: Optional[float] = None
    distance_from_or_low: Optional[float] = None
    
    # Breakout tracking
    breakout_delay_minutes: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class FeatureTableBuilder:
    """Build feature table from raw bar data.
    
    Orchestrates feature calculation and creates unified feature matrix.
    
    Example:
        >>> builder = FeatureTableBuilder(instrument="ES")
        >>> builder.add_dual_or(dual_or_state)
        >>> builder.add_auction_metrics(auction_metrics)
        >>> for bar in bars:
        ...     features = builder.compute_bar_features(bar)
        >>> df = builder.to_dataframe()
    """
    
    def __init__(
        self,
        instrument: str,
        session_date: str,
    ) -> None:
        """Initialize feature table builder.
        
        Args:
            instrument: Instrument symbol
            session_date: Session date string (YYYY-MM-DD)
        """
        self.instrument = instrument
        self.session_date = session_date
        
        # Stored state
        self.dual_or: Optional[DualORState] = None
        self.auction_metrics: Optional[AuctionMetrics] = None
        self.auction_state: Optional[str] = None
        self.auction_state_confidence: Optional[float] = None
        self.regime_vol: Optional[str] = None
        
        # Feature rows
        self.rows: list[FeatureRow] = []
    
    def set_dual_or(self, dual_or: DualORState) -> None:
        """Set dual OR state.
        
        Args:
            dual_or: DualORState from or_layers
        """
        self.dual_or = dual_or
        logger.debug(f"Set dual OR: micro={dual_or.micro_width:.2f}, primary={dual_or.primary_width:.2f}")
    
    def set_auction_metrics(self, metrics: AuctionMetrics) -> None:
        """Set auction metrics.
        
        Args:
            metrics: AuctionMetrics from auction_metrics
        """
        self.auction_metrics = metrics
        logger.debug(f"Set auction metrics: drive={metrics.drive_energy:.2f}, rotations={metrics.rotations}")
    
    def set_auction_state(
        self,
        state: str,
        confidence: float = 1.0,
    ) -> None:
        """Set classified auction state.
        
        Args:
            state: State string (INITIATIVE, BALANCED, etc.)
            confidence: State confidence 0-1
        """
        self.auction_state = state
        self.auction_state_confidence = confidence
        logger.debug(f"Set auction state: {state} (conf={confidence:.2f})")
    
    def set_regime(self, regime: str) -> None:
        """Set volatility regime.
        
        Args:
            regime: Regime string (LOW, NORMAL, EXPANSION)
        """
        self.regime_vol = regime
    
    def compute_bar_features(
        self,
        bar: pd.Series,
        atr_14: float,
        atr_60: float,
        adr_20: float,
        vwap: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        adx: Optional[float] = None,
    ) -> FeatureRow:
        """Compute feature row for single bar.
        
        Args:
            bar: Bar with OHLCV data
            atr_14: 14-period ATR
            atr_60: 60-period ATR
            adr_20: 20-day ADR
            vwap: Session VWAP (if available)
            volume_ratio: Volume ratio vs expected
            adx: ADX value (if available)
            
        Returns:
            FeatureRow with computed features
        """
        # Base features
        row = FeatureRow(
            ts=bar["timestamp_utc"],
            instrument=self.instrument,
            session_date=self.session_date,
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=bar["volume"],
            atr_14=atr_14,
            atr_60=atr_60,
            adr_20=adr_20,
            ret_1m=0.0,  # Computed externally or via log return
        )
        
        # OR features (if available)
        if self.dual_or is not None:
            row.or_micro_high = self.dual_or.micro_high
            row.or_micro_low = self.dual_or.micro_low
            row.or_micro_width = self.dual_or.micro_width
            row.or_micro_width_norm = self.dual_or.micro_width_norm
            row.or_micro_finalized = self.dual_or.micro_finalized
            
            row.or_primary_high = self.dual_or.primary_high
            row.or_primary_low = self.dual_or.primary_low
            row.or_primary_width = self.dual_or.primary_width
            row.or_primary_width_norm = self.dual_or.primary_width_norm
            row.or_primary_duration_used = self.dual_or.primary_duration_used
            row.or_primary_finalized = self.dual_or.primary_finalized
            
            # Distance from OR
            if self.dual_or.primary_finalized:
                row.distance_from_or_high = bar["close"] - self.dual_or.primary_high
                row.distance_from_or_low = bar["close"] - self.dual_or.primary_low
        
        # Auction metrics (if available)
        if self.auction_metrics is not None:
            row.drive_energy = self.auction_metrics.drive_energy
            row.rotations = self.auction_metrics.rotations
            row.vol_z = self.auction_metrics.volume_z
            row.gap_type = self.auction_metrics.gap_type.value
            row.gap_size_norm = self.auction_metrics.gap_size_norm
            row.overnight_range_pct = self.auction_metrics.overnight_range_pct
        
        # VWAP features
        if vwap is not None:
            row.vwap = vwap
            if atr_14 > 0:
                row.vwap_dev_norm = (bar["close"] - vwap) / atr_14
        
        # Volume features
        if volume_ratio is not None:
            row.volume_ratio = volume_ratio
            row.volume_spike = volume_ratio > 1.5  # Spike threshold
        
        # ADX
        if adx is not None:
            row.adx = adx
        
        # State classification
        row.auction_state = self.auction_state
        row.auction_state_confidence = self.auction_state_confidence
        row.regime_vol = self.regime_vol
        
        # Store row
        self.rows.append(row)
        
        return row
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert accumulated rows to DataFrame.
        
        Returns:
            DataFrame with feature matrix
        """
        if not self.rows:
            logger.warning("No feature rows to convert")
            return pd.DataFrame()
        
        records = [row.to_dict() for row in self.rows]
        df = pd.DataFrame(records)
        
        # Set timestamp as index
        df = df.set_index("ts")
        
        logger.info(f"Created feature table: {len(df)} rows, {len(df.columns)} columns")
        
        return df
    
    def save(self, output_path: str) -> None:
        """Save feature table to parquet.
        
        Args:
            output_path: Output parquet path
        """
        df = self.to_dataframe()
        df.to_parquet(output_path, index=True, compression="snappy")
        logger.info(f"Saved feature table to {output_path}")


def load_feature_table(path: str) -> pd.DataFrame:
    """Load feature table from parquet.
    
    Args:
        path: Parquet file path
        
    Returns:
        DataFrame with feature matrix
    """
    df = pd.read_parquet(path)
    logger.info(f"Loaded feature table: {len(df)} rows from {path}")
    return df


def compute_breakout_delay(
    row: FeatureRow,
    or_end_ts: datetime,
) -> float:
    """Compute breakout delay in minutes from OR end.
    
    Args:
        row: Feature row at breakout
        or_end_ts: OR end timestamp
        
    Returns:
        Delay in minutes
    """
    if row.ts < or_end_ts:
        return 0.0
    
    delta = row.ts - or_end_ts
    return delta.total_seconds() / 60.0

