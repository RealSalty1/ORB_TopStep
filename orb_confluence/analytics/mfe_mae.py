"""MFE/MAE tracking and analysis for ORB 2.0.

Tracks maximum favorable and adverse excursions during trade lifetime.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

import pandas as pd
from loguru import logger


@dataclass
class MFEMAESnapshot:
    """Snapshot of MFE/MAE at a point in time."""
    
    timestamp: datetime
    price: float
    mfe_r: float
    mae_r: float


@dataclass
class MFEMAEAnalysis:
    """Complete MFE/MAE analysis for a trade."""
    
    trade_id: str
    direction: str
    entry_price: float
    exit_price: float
    entry_timestamp: datetime
    exit_timestamp: datetime
    
    # Excursions
    mfe_r: float  # Max favorable excursion
    mae_r: float  # Max adverse excursion
    mfe_timestamp: Optional[datetime] = None
    mae_timestamp: Optional[datetime] = None
    
    # Path metrics
    bars_to_mfe: int = 0
    bars_to_mae: int = 0
    mfe_before_mae: bool = True  # Did MFE occur before MAE?
    
    # Exit analysis
    exit_reason: str = "UNKNOWN"
    efficiency: float = 0.0  # realized / MFE
    giveback_r: float = 0.0  # MFE - realized
    
    # Metadata
    tags: Dict = field(default_factory=dict)


class MFEMAETracker:
    """Tracks MFE/MAE for an active trade.
    
    Example:
        >>> tracker = MFEMAETracker(
        ...     trade_id="LONG_001",
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_stop=4995.0,
        ...     entry_timestamp=datetime.now()
        ... )
        >>> 
        >>> for bar in bars:
        ...     tracker.update(bar)
        >>> 
        >>> analysis = tracker.finalize(exit_price=5007.5, exit_reason="TARGET")
    """
    
    def __init__(
        self,
        trade_id: str,
        direction: str,
        entry_price: float,
        initial_stop: float,
        entry_timestamp: datetime,
        tags: Optional[Dict] = None,
    ):
        """Initialize MFE/MAE tracker.
        
        Args:
            trade_id: Trade identifier
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop price
            entry_timestamp: Entry timestamp
            tags: Optional metadata tags
        """
        self.trade_id = trade_id
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.initial_stop = initial_stop
        self.entry_timestamp = entry_timestamp
        self.tags = tags or {}
        
        # Compute initial risk
        self.initial_risk = abs(entry_price - initial_stop)
        
        # Track excursions
        self.mfe_r = 0.0
        self.mae_r = 0.0
        self.mfe_timestamp: Optional[datetime] = None
        self.mae_timestamp: Optional[datetime] = None
        self.mfe_bar_idx = 0
        self.mae_bar_idx = 0
        
        # History
        self.snapshots: List[MFEMAESnapshot] = []
        self.bar_count = 0
    
    def update(self, bar: pd.Series) -> None:
        """Update with new bar.
        
        Args:
            bar: Bar with timestamp_utc, high, low
        """
        self.bar_count += 1
        
        timestamp = bar["timestamp_utc"]
        high = bar["high"]
        low = bar["low"]
        
        # Calculate R from high/low
        if self.direction == "long":
            r_from_high = (high - self.entry_price) / self.initial_risk
            r_from_low = (low - self.entry_price) / self.initial_risk
            
            # Update MFE (high)
            if r_from_high > self.mfe_r:
                self.mfe_r = r_from_high
                self.mfe_timestamp = timestamp
                self.mfe_bar_idx = self.bar_count
            
            # Update MAE (low)
            if r_from_low < self.mae_r:
                self.mae_r = r_from_low
                self.mae_timestamp = timestamp
                self.mae_bar_idx = self.bar_count
        
        else:  # short
            r_from_high = (self.entry_price - high) / self.initial_risk
            r_from_low = (self.entry_price - low) / self.initial_risk
            
            # Update MFE (low)
            if r_from_low > self.mfe_r:
                self.mfe_r = r_from_low
                self.mfe_timestamp = timestamp
                self.mfe_bar_idx = self.bar_count
            
            # Update MAE (high)
            if r_from_high < self.mae_r:
                self.mae_r = r_from_high
                self.mae_timestamp = timestamp
                self.mae_bar_idx = self.bar_count
        
        # Store snapshot
        self.snapshots.append(MFEMAESnapshot(
            timestamp=timestamp,
            price=(high + low) / 2,  # Midpoint
            mfe_r=self.mfe_r,
            mae_r=self.mae_r,
        ))
    
    def finalize(
        self,
        exit_price: float,
        exit_reason: str,
        exit_timestamp: Optional[datetime] = None,
    ) -> MFEMAEAnalysis:
        """Finalize tracking and create analysis.
        
        Args:
            exit_price: Exit price
            exit_reason: Exit reason
            exit_timestamp: Exit timestamp
            
        Returns:
            MFEMAEAnalysis with complete statistics
        """
        if exit_timestamp is None and self.snapshots:
            exit_timestamp = self.snapshots[-1].timestamp
        elif exit_timestamp is None:
            exit_timestamp = self.entry_timestamp
        
        # Calculate realized R
        if self.direction == "long":
            realized_r = (exit_price - self.entry_price) / self.initial_risk
        else:
            realized_r = (self.entry_price - exit_price) / self.initial_risk
        
        # Calculate efficiency and giveback
        if self.mfe_r > 0:
            efficiency = realized_r / self.mfe_r
            giveback_r = self.mfe_r - realized_r
        else:
            efficiency = 0.0
            giveback_r = 0.0
        
        # Determine MFE/MAE order
        mfe_before_mae = self.mfe_bar_idx <= self.mae_bar_idx
        
        return MFEMAEAnalysis(
            trade_id=self.trade_id,
            direction=self.direction,
            entry_price=self.entry_price,
            exit_price=exit_price,
            entry_timestamp=self.entry_timestamp,
            exit_timestamp=exit_timestamp,
            mfe_r=self.mfe_r,
            mae_r=self.mae_r,
            mfe_timestamp=self.mfe_timestamp,
            mae_timestamp=self.mae_timestamp,
            bars_to_mfe=self.mfe_bar_idx,
            bars_to_mae=self.mae_bar_idx,
            mfe_before_mae=mfe_before_mae,
            exit_reason=exit_reason,
            efficiency=efficiency,
            giveback_r=giveback_r,
            tags=self.tags,
        )
    
    def get_path_df(self) -> pd.DataFrame:
        """Get MFE/MAE path as DataFrame.
        
        Returns:
            DataFrame with timestamp, price, mfe_r, mae_r
        """
        return pd.DataFrame([
            {
                'timestamp': snap.timestamp,
                'price': snap.price,
                'mfe_r': snap.mfe_r,
                'mae_r': snap.mae_r,
            }
            for snap in self.snapshots
        ])


def aggregate_mfe_mae_stats(analyses: List[MFEMAEAnalysis]) -> Dict:
    """Aggregate MFE/MAE statistics across trades.
    
    Args:
        analyses: List of MFEMAEAnalysis
        
    Returns:
        Dictionary with aggregate statistics
    """
    if not analyses:
        return {}
    
    winners = [a for a in analyses if (a.exit_price - a.entry_price) * (1 if a.direction == "long" else -1) > 0]
    losers = [a for a in analyses if (a.exit_price - a.entry_price) * (1 if a.direction == "long" else -1) <= 0]
    
    stats = {
        'total_trades': len(analyses),
        'avg_mfe': sum(a.mfe_r for a in analyses) / len(analyses),
        'avg_mae': sum(a.mae_r for a in analyses) / len(analyses),
        'avg_efficiency': sum(a.efficiency for a in analyses) / len(analyses),
        'avg_giveback': sum(a.giveback_r for a in analyses) / len(analyses),
        
        # Winners
        'winner_avg_mfe': sum(a.mfe_r for a in winners) / len(winners) if winners else 0.0,
        'winner_avg_mae': sum(a.mae_r for a in winners) / len(winners) if winners else 0.0,
        'winner_avg_efficiency': sum(a.efficiency for a in winners) / len(winners) if winners else 0.0,
        
        # Losers
        'loser_avg_mfe': sum(a.mfe_r for a in losers) / len(losers) if losers else 0.0,
        'loser_avg_mae': sum(a.mae_r for a in losers) / len(losers) if losers else 0.0,
    }
    
    return stats
