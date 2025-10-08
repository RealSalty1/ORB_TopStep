"""Partial exit management for multi-stage profit taking.

Handles:
- Partial fills at target levels
- Position size tracking
- Remaining runner management
- Target sequencing
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from loguru import logger


@dataclass
class PartialTarget:
    """Partial profit target definition."""
    
    target_r: float  # Target in R-multiples
    size_fraction: float  # Fraction of position (0-1)
    price: Optional[float] = None  # Computed target price
    hit: bool = False
    hit_timestamp: Optional[datetime] = None
    hit_price: Optional[float] = None
    
    def __repr__(self) -> str:
        """String representation."""
        status = "HIT" if self.hit else "PENDING"
        return f"Target({self.target_r:.1f}R, {self.size_fraction:.0%}) [{status}]"


@dataclass
class PartialFillEvent:
    """Partial fill execution event."""
    
    timestamp: datetime
    target_number: int
    target_r: float
    size_fraction: float
    exit_price: float
    remaining_size: float
    realized_r: float
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"PartialFill(T{self.target_number} @ {self.exit_price:.2f}, "
            f"{self.size_fraction:.0%} at {self.realized_r:.2f}R, "
            f"remaining={self.remaining_size:.0%})"
        )


class PartialExitManager:
    """Manages partial profit targets and position scaling.
    
    Example:
        >>> manager = PartialExitManager(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_risk=5.0,
        ...     targets=[
        ...         PartialTarget(target_r=1.0, size_fraction=0.5),
        ...         PartialTarget(target_r=1.5, size_fraction=0.25),
        ...     ]
        ... )
        >>> 
        >>> # On each bar
        >>> fills = manager.check_targets(current_price=5007.5, timestamp=now)
        >>> for fill in fills:
        ...     print(f"Partial filled: {fill}")
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_risk: float,
        targets: List[PartialTarget],
    ) -> None:
        """Initialize partial exit manager.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_risk: Initial risk (for R calculations)
            targets: List of partial targets (ordered by target_r)
        """
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.initial_risk = initial_risk
        self.targets = sorted(targets, key=lambda t: t.target_r)
        
        # Compute target prices
        for target in self.targets:
            if self.direction == "long":
                target.price = entry_price + (target.target_r * initial_risk)
            else:  # short
                target.price = entry_price - (target.target_r * initial_risk)
        
        # Position tracking
        self.remaining_size = 1.0
        self.partial_fills: List[PartialFillEvent] = []
        self.all_targets_hit = False
    
    def check_targets(
        self,
        current_price: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
    ) -> List[PartialFillEvent]:
        """Check if any targets hit on this bar.
        
        Args:
            current_price: Current price (close)
            bar_high: Bar high
            bar_low: Bar low
            timestamp: Current timestamp
            
        Returns:
            List of PartialFillEvent (can be empty)
        """
        fills = []
        
        for i, target in enumerate(self.targets):
            if target.hit:
                continue
            
            # Check if target price touched
            hit = False
            if self.direction == "long":
                hit = bar_high >= target.price
                fill_price = target.price  # Assume filled at target
            else:  # short
                hit = bar_low <= target.price
                fill_price = target.price
            
            if hit:
                # Mark target as hit
                target.hit = True
                target.hit_timestamp = timestamp
                target.hit_price = fill_price
                
                # Reduce position
                self.remaining_size -= target.size_fraction
                self.remaining_size = max(0.0, self.remaining_size)  # Clamp to 0
                
                # Create fill event
                fill = PartialFillEvent(
                    timestamp=timestamp,
                    target_number=i + 1,
                    target_r=target.target_r,
                    size_fraction=target.size_fraction,
                    exit_price=fill_price,
                    remaining_size=self.remaining_size,
                    realized_r=target.target_r,
                )
                
                fills.append(fill)
                self.partial_fills.append(fill)
                
                logger.info(f"Partial target hit: {fill}")
        
        # Check if all targets hit
        if all(t.hit for t in self.targets):
            self.all_targets_hit = True
        
        return fills
    
    def get_next_target(self) -> Optional[PartialTarget]:
        """Get next unhit target.
        
        Returns:
            Next PartialTarget or None if all hit
        """
        for target in self.targets:
            if not target.hit:
                return target
        return None
    
    def has_runner(self) -> bool:
        """Check if position has remaining runner.
        
        Returns:
            True if remaining_size > 0
        """
        return self.remaining_size > 0
    
    def compute_weighted_realized_r(self) -> float:
        """Compute weighted realized R from partial fills.
        
        Returns:
            Weighted average R
        """
        if not self.partial_fills:
            return 0.0
        
        total_weighted = sum(
            fill.realized_r * fill.size_fraction
            for fill in self.partial_fills
        )
        
        total_fraction = sum(fill.size_fraction for fill in self.partial_fills)
        
        if total_fraction > 0:
            return total_weighted / total_fraction
        return 0.0


class TimeDecayExitManager:
    """Manages time-based exit conditions.
    
    Exits trade if:
    1. Max time in trade exceeded
    2. MFE/time slope decays below threshold
    3. No progress toward target in window
    
    Example:
        >>> manager = TimeDecayExitManager(
        ...     max_bars=120,
        ...     slope_window=20,
        ...     slope_threshold=0.01
        ... )
    """
    
    def __init__(
        self,
        max_bars: Optional[int] = None,
        slope_window: int = 20,
        slope_threshold: float = 0.01,
        no_progress_bars: int = 30,
        no_progress_threshold_r: float = 0.1,
    ) -> None:
        """Initialize time decay manager.
        
        Args:
            max_bars: Max bars in trade (None = no limit)
            slope_window: Window for slope calculation
            slope_threshold: Min MFE/time slope to continue
            no_progress_bars: Bars to check for progress
            no_progress_threshold_r: Min R progress required
        """
        self.max_bars = max_bars
        self.slope_window = slope_window
        self.slope_threshold = slope_threshold
        self.no_progress_bars = no_progress_bars
        self.no_progress_threshold = no_progress_threshold_r
        
        # State tracking
        self.bars_in_trade = 0
        self.mfe_history: List[float] = []
        self.entry_timestamp: Optional[datetime] = None
    
    def update(
        self,
        current_mfe_r: float,
        timestamp: datetime,
    ) -> Optional[str]:
        """Check time decay exit conditions.
        
        Args:
            current_mfe_r: Current MFE in R
            timestamp: Current timestamp
            
        Returns:
            Exit reason if time exit triggered, None otherwise
        """
        if self.entry_timestamp is None:
            self.entry_timestamp = timestamp
        
        self.bars_in_trade += 1
        self.mfe_history.append(current_mfe_r)
        
        # Check max bars
        if self.max_bars is not None and self.bars_in_trade >= self.max_bars:
            return f"MAX_BARS: {self.bars_in_trade} bars in trade"
        
        # Check slope decay (need sufficient history)
        if len(self.mfe_history) >= self.slope_window:
            recent_mfe = self.mfe_history[-self.slope_window:]
            
            # Compute linear slope
            x = list(range(len(recent_mfe)))
            y = recent_mfe
            
            # Simple linear regression
            n = len(x)
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            
            if denominator > 0:
                slope = numerator / denominator
                
                if slope < self.slope_threshold:
                    return f"SLOPE_DECAY: slope={slope:.4f} < {self.slope_threshold}"
        
        # Check no progress
        if self.bars_in_trade >= self.no_progress_bars:
            recent_progress = current_mfe_r - self.mfe_history[-self.no_progress_bars]
            
            if recent_progress < self.no_progress_threshold:
                return (
                    f"NO_PROGRESS: {recent_progress:.2f}R in "
                    f"{self.no_progress_bars} bars"
                )
        
        return None
    
    def reset(self):
        """Reset for new trade."""
        self.bars_in_trade = 0
        self.mfe_history = []
        self.entry_timestamp = None

