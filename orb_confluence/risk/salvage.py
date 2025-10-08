"""Salvage abort logic for trade path management.

Detects trades that achieved significant MFE but are giving back gains,
and exits before full stop hit to reduce loss magnitude.

Salvage conditions:
1. MFE >= salvage_trigger_r (e.g., 0.4R)
2. Current retrace >= retrace_threshold (e.g., 65% of MFE)
3. Bars since peak >= confirmation_bars (e.g., 6)
4. No reclaim of fractional recovery (e.g., not back above 50% of MFE)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger


@dataclass
class SalvageConditions:
    """Salvage trigger conditions configuration."""
    
    # Core thresholds
    trigger_mfe_r: float = 0.4  # Min MFE to enable salvage
    retrace_threshold: float = 0.65  # Min retrace % of MFE
    confirmation_bars: int = 6  # Bars to wait after retrace
    recovery_threshold: float = 0.5  # Disable if price recovers above this % of MFE
    
    # Optional time-based
    max_bars_from_peak: Optional[int] = None  # Max bars allowed from peak
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SalvageConditions(trigger={self.trigger_mfe_r:.2f}R, "
            f"retrace={self.retrace_threshold:.0%}, "
            f"confirm={self.confirmation_bars} bars)"
        )


@dataclass
class SalvageEvent:
    """Salvage exit event record."""
    
    timestamp: datetime
    mfe_r: float  # Peak MFE achieved
    current_r: float  # Current R at salvage
    retrace_ratio: float  # Retrace as % of MFE
    bars_since_peak: int
    exit_price: float
    salvage_benefit_r: float  # How much better than full stop
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SalvageEvent(MFE={self.mfe_r:.2f}R, current={self.current_r:.2f}R, "
            f"retrace={self.retrace_ratio:.0%}, bars={self.bars_since_peak}, "
            f"benefit={self.salvage_benefit_r:.2f}R)"
        )


class SalvageManager:
    """Manages salvage abort detection for a trade.
    
    Tracks MFE progression and detects give-back patterns that warrant early exit.
    
    Example:
        >>> manager = SalvageManager(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_risk=5.0,
        ...     conditions=SalvageConditions()
        ... )
        >>> 
        >>> # On each bar
        >>> salvage_event = manager.evaluate(
        ...     current_price=5002.0,
        ...     current_mfe_r=1.2,
        ...     current_r=0.3,
        ...     timestamp=datetime.now()
        ... )
        >>> 
        >>> if salvage_event:
        ...     # Exit trade via salvage
        ...     print(f"Salvage exit: {salvage_event}")
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_risk: float,
        initial_stop: float,
        conditions: Optional[SalvageConditions] = None,
    ) -> None:
        """Initialize salvage manager.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_risk: Initial risk (|entry - initial_stop|)
            initial_stop: Initial stop price
            conditions: Salvage conditions (defaults if None)
        """
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.initial_risk = initial_risk
        self.initial_stop = initial_stop
        self.conditions = conditions or SalvageConditions()
        
        # State tracking
        self.peak_mfe_r = 0.0
        self.peak_price = entry_price
        self.peak_timestamp: Optional[datetime] = None
        self.bars_since_peak = 0
        self.salvage_armed = False  # True once MFE >= trigger
        self.salvage_triggered = False
        self.retrace_confirmation_bars = 0
        
        # Performance tracking
        self.total_salvage_checks = 0
        self.false_salvage_count = 0  # Times we recovered after retrace
    
    def evaluate(
        self,
        current_price: float,
        current_mfe_r: float,
        current_r: float,
        timestamp: datetime,
    ) -> Optional[SalvageEvent]:
        """Evaluate salvage conditions.
        
        Args:
            current_price: Current market price
            current_mfe_r: Current MFE in R-multiples
            current_r: Current R (P&L)
            timestamp: Current timestamp
            
        Returns:
            SalvageEvent if salvage triggered, None otherwise
        """
        self.total_salvage_checks += 1
        
        # Update peak tracking
        if current_mfe_r > self.peak_mfe_r:
            self.peak_mfe_r = current_mfe_r
            self.peak_price = current_price
            self.peak_timestamp = timestamp
            self.bars_since_peak = 0
            self.retrace_confirmation_bars = 0
            
            # Check if salvage should be armed
            if current_mfe_r >= self.conditions.trigger_mfe_r:
                self.salvage_armed = True
                logger.debug(f"Salvage armed at {current_mfe_r:.2f}R MFE")
        else:
            self.bars_since_peak += 1
        
        # Only evaluate if armed
        if not self.salvage_armed:
            return None
        
        # Already triggered
        if self.salvage_triggered:
            return None
        
        # Compute retrace from peak
        if self.peak_mfe_r > 0:
            retrace_ratio = (self.peak_mfe_r - current_r) / self.peak_mfe_r
        else:
            retrace_ratio = 0.0
        
        # Check recovery (if price recovers, reset confirmation)
        recovery_r = current_r / self.peak_mfe_r if self.peak_mfe_r > 0 else 0.0
        if recovery_r >= self.conditions.recovery_threshold:
            if self.retrace_confirmation_bars > 0:
                logger.debug(
                    f"Trade recovered to {recovery_r:.0%} of peak MFE, "
                    f"resetting salvage confirmation"
                )
                self.false_salvage_count += 1
            self.retrace_confirmation_bars = 0
            return None
        
        # Check retrace threshold
        if retrace_ratio >= self.conditions.retrace_threshold:
            self.retrace_confirmation_bars += 1
        else:
            self.retrace_confirmation_bars = 0
            return None
        
        # Check confirmation bars
        if self.retrace_confirmation_bars < self.conditions.confirmation_bars:
            return None
        
        # Optional max bars check
        if (
            self.conditions.max_bars_from_peak is not None
            and self.bars_since_peak > self.conditions.max_bars_from_peak
        ):
            logger.debug(
                f"Salvage disabled: {self.bars_since_peak} bars from peak "
                f"exceeds max {self.conditions.max_bars_from_peak}"
            )
            return None
        
        # Salvage triggered!
        self.salvage_triggered = True
        
        # Compute benefit (how much better than full stop)
        stop_loss_r = -1.0  # Would have been -1R at full stop
        salvage_benefit_r = current_r - stop_loss_r
        
        event = SalvageEvent(
            timestamp=timestamp,
            mfe_r=self.peak_mfe_r,
            current_r=current_r,
            retrace_ratio=retrace_ratio,
            bars_since_peak=self.bars_since_peak,
            exit_price=current_price,
            salvage_benefit_r=salvage_benefit_r,
        )
        
        logger.info(
            f"Salvage exit triggered: MFE {self.peak_mfe_r:.2f}R → "
            f"current {current_r:.2f}R ({retrace_ratio:.0%} retrace), "
            f"benefit {salvage_benefit_r:.2f}R vs full stop"
        )
        
        return event
    
    @property
    def is_armed(self) -> bool:
        """Check if salvage is armed (MFE exceeded trigger)."""
        return self.salvage_armed
    
    @property
    def is_triggered(self) -> bool:
        """Check if salvage has been triggered."""
        return self.salvage_triggered
    
    def get_stats(self) -> dict:
        """Get salvage manager statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            "armed": self.salvage_armed,
            "triggered": self.salvage_triggered,
            "peak_mfe_r": self.peak_mfe_r,
            "bars_since_peak": self.bars_since_peak,
            "total_checks": self.total_salvage_checks,
            "false_salvages": self.false_salvage_count,
        }


def analyze_salvage_performance(
    trades_with_salvage: list,
    trades_without_salvage: list,
) -> dict:
    """Analyze salvage system performance.
    
    Compares outcomes with salvage vs hypothetical no-salvage.
    
    Args:
        trades_with_salvage: Trades that used salvage exit
        trades_without_salvage: Hypothetical trades without salvage
        
    Returns:
        Dictionary with performance comparison
    """
    if not trades_with_salvage:
        return {
            "n_salvage_trades": 0,
            "avg_benefit_r": 0.0,
            "total_benefit_r": 0.0,
            "salvage_rate": 0.0,
        }
    
    # Compute benefits
    benefits = [t.salvage_benefit_r for t in trades_with_salvage]
    avg_benefit = sum(benefits) / len(benefits)
    total_benefit = sum(benefits)
    
    # Compare average loss
    avg_loss_with = sum(t.current_r for t in trades_with_salvage) / len(trades_with_salvage)
    avg_loss_without = -1.0  # Would have been full -1R
    
    return {
        "n_salvage_trades": len(trades_with_salvage),
        "avg_benefit_r": avg_benefit,
        "total_benefit_r": total_benefit,
        "salvage_rate": len(trades_with_salvage) / (len(trades_with_salvage) + len(trades_without_salvage)),
        "avg_loss_with_salvage": avg_loss_with,
        "avg_loss_without_salvage": avg_loss_without,
        "loss_reduction": avg_loss_without - avg_loss_with,
    }

