"""Trade state dataclasses for tracking active positions.

Defines the core data structures for trade signals and active trade tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class TradeSignal:
    """Trade signal with entry details and confluence metadata.
    
    Attributes:
        direction: 'long' or 'short'
        timestamp: Signal timestamp
        entry_price: Entry price (trigger price)
        confluence_score: Total confluence score
        confluence_required: Required score for entry
        factors: Factor activation flags
        or_high: Opening Range high
        or_low: Opening Range low
        signal_id: Unique identifier
    """
    
    direction: str
    timestamp: datetime
    entry_price: float
    confluence_score: float
    confluence_required: float
    factors: Dict[str, float]
    or_high: float
    or_low: float
    signal_id: str
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TradeSignal({self.direction.upper()} @ {self.entry_price:.2f}, "
            f"score={self.confluence_score:.1f}/{self.confluence_required:.1f}, "
            f"id={self.signal_id})"
        )


@dataclass
class PartialFill:
    """Record of a partial target fill.
    
    Attributes:
        timestamp: Fill timestamp
        price: Fill price
        size_fraction: Fraction of position closed (e.g., 0.5 = 50%)
        target_number: Target number (1, 2, etc.)
        r_multiple: R achieved at this fill
    """
    
    timestamp: datetime
    price: float
    size_fraction: float
    target_number: int
    r_multiple: float


@dataclass
class ActiveTrade:
    """Active trade with full state tracking.
    
    Tracks an open position from entry through exit, including partial fills,
    stop adjustments, and R-multiple progression.
    
    Attributes:
        trade_id: Unique trade identifier
        direction: 'long' or 'short'
        entry_timestamp: Entry time
        entry_price: Entry price
        stop_price_initial: Initial stop price
        stop_price_current: Current stop price (may move to breakeven)
        targets: List of (price, size_fraction) tuples
        remaining_size: Remaining position size (1.0 = full, 0.5 = half)
        partials_filled: List of PartialFill objects
        moved_to_breakeven: Whether stop moved to breakeven
        breakeven_price: Breakeven price (entry + buffer)
        exit_timestamp: Exit timestamp (None if still open)
        exit_price: Exit price (None if still open)
        exit_reason: Exit reason ('stop', 'target', 'governance', etc.)
        realized_r: Realized R-multiple (final)
        max_favorable_r: Maximum favorable excursion (R)
        max_adverse_r: Maximum adverse excursion (R)
        
        # Metadata
        signal: Original trade signal
        initial_risk: Initial risk (|entry - stop|)
    """
    
    trade_id: str
    direction: str
    entry_timestamp: datetime
    entry_price: float
    stop_price_initial: float
    stop_price_current: float
    targets: List[Tuple[float, float]]
    
    # State tracking
    remaining_size: float = 1.0
    partials_filled: List[PartialFill] = field(default_factory=list)
    moved_to_breakeven: bool = False
    breakeven_price: Optional[float] = None
    
    # Exit tracking
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_r: Optional[float] = None
    
    # R tracking
    max_favorable_r: float = 0.0
    max_adverse_r: float = 0.0
    
    # Metadata
    signal: Optional[TradeSignal] = None
    initial_risk: Optional[float] = None
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.initial_risk is None:
            self.initial_risk = abs(self.entry_price - self.stop_price_initial)
    
    @property
    def is_open(self) -> bool:
        """Check if trade is still open."""
        return self.exit_timestamp is None
    
    @property
    def is_closed(self) -> bool:
        """Check if trade is closed."""
        return not self.is_open
    
    def compute_current_r(self, current_price: float) -> float:
        """Compute current R-multiple.
        
        Args:
            current_price: Current market price.
            
        Returns:
            Current R-multiple (positive = profit, negative = loss).
        """
        if self.initial_risk <= 0:
            return 0.0
        
        if self.direction == 'long':
            pnl = current_price - self.entry_price
        else:  # short
            pnl = self.entry_price - current_price
        
        return pnl / self.initial_risk
    
    def update_r_extremes(self, current_price: float) -> None:
        """Update max favorable and adverse R.
        
        Args:
            current_price: Current market price.
        """
        current_r = self.compute_current_r(current_price)
        
        # Update favorable excursion
        if current_r > self.max_favorable_r:
            self.max_favorable_r = current_r
        
        # Update adverse excursion
        if current_r < self.max_adverse_r:
            self.max_adverse_r = current_r
    
    def __repr__(self) -> str:
        """String representation."""
        status = "OPEN" if self.is_open else "CLOSED"
        return (
            f"ActiveTrade({self.trade_id} {self.direction.upper()} {status}, "
            f"entry={self.entry_price:.2f}, stop={self.stop_price_current:.2f}, "
            f"remaining={self.remaining_size:.0%})"
        )