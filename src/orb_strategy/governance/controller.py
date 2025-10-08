"""Governance controller for risk discipline.

Implements:
- Daily signal caps
- Consecutive loss lockouts
- Time cutoffs
- Session-end flattening
"""

from dataclasses import dataclass, field
from datetime import datetime, time, date
from typing import Dict, List

from loguru import logger

from ..config import GovernanceConfig
from ..execution.position import Position, ExitReason


@dataclass
class DayState:
    """State tracking for a single trading day."""

    date: date
    signals_fired: int = 0
    consecutive_losses: int = 0
    locked_out: bool = False
    positions_opened: List[str] = field(default_factory=list)  # Trade IDs
    positions_closed: List[str] = field(default_factory=list)


@dataclass
class GovernanceState:
    """Global governance state."""

    current_date: Optional[date] = None
    day_states: Dict[date, DayState] = field(default_factory=dict)
    global_consecutive_losses: int = 0
    global_lockout: bool = False


class GovernanceController:
    """Controls risk governance rules.

    Prevents overtrading and enforces discipline through:
    - Daily signal limits
    - Consecutive loss lockouts
    - Time-based restrictions
    """

    def __init__(self, config: GovernanceConfig) -> None:
        """Initialize governance controller.

        Args:
            config: Governance configuration.
        """
        self.config = config
        self.state = GovernanceState()

    def can_take_signal(
        self,
        symbol: str,
        current_time: datetime,
    ) -> tuple[bool, str]:
        """Check if a new signal can be taken.

        Args:
            symbol: Instrument symbol.
            current_time: Current timestamp.

        Returns:
            Tuple of (allowed, reason_if_blocked).
        """
        current_date = current_time.date()

        # Initialize day state if needed
        if current_date not in self.state.day_states:
            self._initialize_day(current_date)

        day_state = self.state.day_states[current_date]

        # Check global lockout
        if self.state.global_lockout:
            return False, "Global lockout active due to consecutive losses"

        # Check day lockout
        if day_state.locked_out:
            return False, f"Day locked out after {day_state.consecutive_losses} consecutive losses"

        # Check daily signal cap
        if day_state.signals_fired >= self.config.max_signals_per_day:
            return (
                False,
                f"Daily signal cap reached ({self.config.max_signals_per_day})",
            )

        # Check time cutoff
        if self.config.time_cutoff is not None:
            current_time_only = current_time.time()
            if current_time_only >= self.config.time_cutoff:
                return False, f"Time cutoff reached ({self.config.time_cutoff})"

        return True, ""

    def record_signal(
        self,
        symbol: str,
        current_time: datetime,
    ) -> None:
        """Record that a signal was fired.

        Args:
            symbol: Instrument symbol.
            current_time: Current timestamp.
        """
        current_date = current_time.date()

        if current_date not in self.state.day_states:
            self._initialize_day(current_date)

        day_state = self.state.day_states[current_date]
        day_state.signals_fired += 1

        logger.debug(
            f"Signal recorded for {symbol} on {current_date}, "
            f"total today: {day_state.signals_fired}"
        )

    def record_position_opened(
        self,
        position: Position,
    ) -> None:
        """Record that a position was opened.

        Args:
            position: Position that was opened.
        """
        pos_date = position.entry_time.date()

        if pos_date not in self.state.day_states:
            self._initialize_day(pos_date)

        day_state = self.state.day_states[pos_date]
        day_state.positions_opened.append(position.trade_id)

    def record_position_closed(
        self,
        position: Position,
    ) -> None:
        """Record that a position was closed and update loss tracking.

        Args:
            position: Position that was closed.
        """
        if not position.is_closed:
            return

        close_date = position.final_exit_time.date()

        if close_date not in self.state.day_states:
            self._initialize_day(close_date)

        day_state = self.state.day_states[close_date]
        day_state.positions_closed.append(position.trade_id)

        # Check if this was a full stop loss
        is_full_stop = (
            position.final_exit_reason == ExitReason.STOP
            and len(position.partials) == 0  # No partials taken
        )

        if is_full_stop:
            # Update consecutive loss counters
            day_state.consecutive_losses += 1
            self.state.global_consecutive_losses += 1

            logger.info(
                f"Full stop loss recorded for {position.trade_id}, "
                f"consecutive losses: {self.state.global_consecutive_losses}"
            )

            # Check for lockout
            if day_state.consecutive_losses >= self.config.lockout_after_losses:
                day_state.locked_out = True
                logger.warning(
                    f"Day lockout triggered on {close_date} "
                    f"after {day_state.consecutive_losses} consecutive losses"
                )

            if self.state.global_consecutive_losses >= self.config.lockout_after_losses:
                self.state.global_lockout = True
                logger.warning(
                    f"Global lockout triggered after "
                    f"{self.state.global_consecutive_losses} consecutive losses"
                )

        else:
            # Reset consecutive loss counter on any non-full-stop exit
            day_state.consecutive_losses = 0
            self.state.global_consecutive_losses = 0
            logger.debug(f"Consecutive loss counter reset after winning/partial trade")

    def should_flatten_for_session_end(
        self,
        current_time: datetime,
        session_end: time,
    ) -> bool:
        """Check if positions should be flattened for session end.

        Args:
            current_time: Current timestamp.
            session_end: Session end time.

        Returns:
            True if should flatten.
        """
        if not self.config.flatten_at_session_end:
            return False

        current_time_only = current_time.time()

        # Flatten positions in last bar before close (simplified check)
        return current_time_only >= session_end

    def reset_for_new_day(self, new_date: date) -> None:
        """Reset state for a new trading day.

        Args:
            new_date: New trading date.
        """
        self._initialize_day(new_date)
        self.state.current_date = new_date

        # Note: Global lockout persists across days until reset manually
        # or until a winning trade

        logger.debug(f"Governance state reset for new day: {new_date}")

    def _initialize_day(self, trading_date: date) -> None:
        """Initialize state for a trading day.

        Args:
            trading_date: Trading date.
        """
        if trading_date not in self.state.day_states:
            self.state.day_states[trading_date] = DayState(date=trading_date)
