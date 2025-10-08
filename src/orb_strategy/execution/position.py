"""Position and trade state management."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from ..signals.detector import Direction


class PositionState(str, Enum):
    """Position lifecycle states."""

    OPEN = "open"
    CLOSED = "closed"


class ExitReason(str, Enum):
    """Position exit reasons."""

    STOP = "stop"
    TARGET_1 = "target_1"
    TARGET_2 = "target_2"
    RUNNER = "runner"
    TIME_EXPIRY = "time_expiry"
    GOVERNANCE_FLATTEN = "governance_flatten"
    SESSION_END = "session_end"


@dataclass
class PartialFill:
    """Partial exit record."""

    timestamp: datetime
    price: float
    quantity: float
    reason: ExitReason
    r_realized: float


@dataclass
class Position:
    """Represents an open or closed trading position.

    Tracks entry, stops, targets, partials, and final exit.
    """

    # Identity
    trade_id: str = field(default_factory=lambda: str(uuid4()))
    symbol: str = ""
    
    # Entry
    direction: Direction = Direction.LONG
    entry_time: datetime = field(default_factory=datetime.utcnow)
    entry_price: float = 0.0
    quantity: float = 1.0
    
    # Stop management
    initial_stop: float = 0.0
    current_stop: float = 0.0
    
    # Targets
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    runner_target: Optional[float] = None
    
    # Partials
    t1_quantity: float = 0.0
    t2_quantity: float = 0.0
    runner_quantity: float = 0.0
    
    remaining_quantity: float = 0.0
    
    # Exit tracking
    state: PositionState = PositionState.OPEN
    partials: List[PartialFill] = field(default_factory=list)
    
    final_exit_time: Optional[datetime] = None
    final_exit_price: Optional[float] = None
    final_exit_reason: Optional[ExitReason] = None
    
    # Performance tracking
    initial_risk: float = 0.0  # |entry - initial_stop|
    max_favorable_excursion: float = 0.0  # Best R achieved
    max_adverse_excursion: float = 0.0  # Worst R drawdown
    realized_r: float = 0.0  # Final R multiple
    
    # Metadata
    or_high: float = 0.0
    or_low: float = 0.0
    or_width: float = 0.0
    or_valid: bool = True
    confluence_score_long: float = 0.0
    confluence_score_short: float = 0.0
    factor_signals: dict = field(default_factory=dict)
    
    breakeven_moved: bool = False

    def __post_init__(self) -> None:
        """Initialize computed fields."""
        self.remaining_quantity = self.quantity
        self.initial_risk = abs(self.entry_price - self.initial_stop)
        self.current_stop = self.initial_stop

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.direction == Direction.LONG

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.direction == Direction.SHORT

    @property
    def is_open(self) -> bool:
        """Check if position is open."""
        return self.state == PositionState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.state == PositionState.CLOSED

    def compute_r(self, price: float) -> float:
        """Compute R multiple at a given price.

        Args:
            price: Current price.

        Returns:
            R multiple (can be negative for loss).
        """
        if self.initial_risk == 0:
            return 0.0

        pnl = (price - self.entry_price) if self.is_long else (self.entry_price - price)
        return pnl / self.initial_risk

    def update_excursion(self, current_price: float) -> None:
        """Update MAE/MFE tracking.

        Args:
            current_price: Current price.
        """
        current_r = self.compute_r(current_price)

        if current_r > self.max_favorable_excursion:
            self.max_favorable_excursion = current_r

        if current_r < self.max_adverse_excursion:
            self.max_adverse_excursion = current_r

    def add_partial_fill(
        self,
        timestamp: datetime,
        price: float,
        quantity: float,
        reason: ExitReason,
    ) -> None:
        """Record a partial exit.

        Args:
            timestamp: Exit timestamp.
            price: Exit price.
            quantity: Quantity exited.
            reason: Exit reason.
        """
        r_realized = self.compute_r(price)

        partial = PartialFill(
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            reason=reason,
            r_realized=r_realized,
        )

        self.partials.append(partial)
        self.remaining_quantity -= quantity

    def close_position(
        self,
        exit_time: datetime,
        exit_price: float,
        exit_reason: ExitReason,
    ) -> None:
        """Close the position completely.

        Args:
            exit_time: Exit timestamp.
            exit_price: Exit price.
            exit_reason: Exit reason.
        """
        self.state = PositionState.CLOSED
        self.final_exit_time = exit_time
        self.final_exit_price = exit_price
        self.final_exit_reason = exit_reason

        # Compute realized R (weighted by partial fills)
        if not self.partials and self.quantity > 0:
            # No partials, simple calculation
            self.realized_r = self.compute_r(exit_price)
        else:
            # Weighted average of partials + remaining
            total_r = 0.0

            for partial in self.partials:
                weight = partial.quantity / self.quantity
                total_r += weight * partial.r_realized

            if self.remaining_quantity > 0:
                weight = self.remaining_quantity / self.quantity
                total_r += weight * self.compute_r(exit_price)

            self.realized_r = total_r

    def to_dict(self) -> dict:
        """Convert position to dict for serialization."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "initial_stop": self.initial_stop,
            "current_stop": self.current_stop,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "runner_target": self.runner_target,
            "state": self.state.value,
            "final_exit_time": self.final_exit_time.isoformat() if self.final_exit_time else None,
            "final_exit_price": self.final_exit_price,
            "final_exit_reason": self.final_exit_reason.value if self.final_exit_reason else None,
            "realized_r": self.realized_r,
            "max_favorable_excursion": self.max_favorable_excursion,
            "max_adverse_excursion": self.max_adverse_excursion,
            "or_high": self.or_high,
            "or_low": self.or_low,
            "or_width": self.or_width,
            "or_valid": self.or_valid,
            "confluence_score_long": self.confluence_score_long,
            "confluence_score_short": self.confluence_score_short,
            "breakeven_moved": self.breakeven_moved,
            "num_partials": len(self.partials),
        }
