"""Governance rules for trade discipline and risk control.

Enforces daily signal caps, loss lockouts, and time cutoffs to prevent
excessive trading and protect capital on difficult days.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional

from loguru import logger


@dataclass
class GovernanceState:
    """Governance state tracking for risk control.
    
    Tracks daily trading activity and enforces discipline rules.
    
    Attributes:
        current_date: Current trading date
        day_signal_count: Number of signals emitted today
        consecutive_losses: Number of consecutive full-stop losses
        daily_realized_r: Cumulative realized R for current day
        lockout_active: Whether trading is locked out
        lockout_reason: Reason for lockout (if active)
        trade_outcomes: List of trade outcomes (True=win, False=loss)
    """
    
    current_date: Optional[datetime.date] = None
    day_signal_count: int = 0
    consecutive_losses: int = 0
    daily_realized_r: float = 0.0
    lockout_active: bool = False
    lockout_reason: Optional[str] = None
    trade_outcomes: list = field(default_factory=list)
    
    def __repr__(self) -> str:
        """String representation."""
        status = "LOCKED OUT" if self.lockout_active else "ACTIVE"
        return (
            f"GovernanceState({self.current_date} {status}: "
            f"signals={self.day_signal_count}, losses={self.consecutive_losses}, "
            f"daily_r={self.daily_realized_r:.2f})"
        )


class GovernanceManager:
    """Manages governance rules and state.
    
    Enforces:
    - Daily signal caps
    - Loss lockouts
    - Time cutoffs
    - Session resets
    
    Example:
        >>> gov = GovernanceManager(
        ...     max_signals_per_day=3,
        ...     lockout_after_losses=2,
        ...     time_cutoff=time(15, 30)
        ... )
        >>> 
        >>> # Check if can emit signal
        >>> if gov.can_emit_signal(current_time):
        ...     # Emit signal
        ...     gov.register_signal_emitted(current_time)
        >>> 
        >>> # Register trade outcome
        >>> gov.register_trade_outcome(win=False)  # Loss
        >>> 
        >>> # Check lockout
        >>> if gov.state.lockout_active:
        ...     print(f"Locked out: {gov.state.lockout_reason}")
    """
    
    def __init__(
        self,
        max_signals_per_day: int = 3,
        lockout_after_losses: int = 2,
        max_daily_loss_r: Optional[float] = None,
        time_cutoff: Optional[time] = None,
        flatten_at_session_end: bool = True,
    ):
        """Initialize governance manager.
        
        Args:
            max_signals_per_day: Maximum signals per day (per instrument).
            lockout_after_losses: Consecutive full-stop losses before lockout.
            max_daily_loss_r: Maximum daily loss in R (halts new entries if reached).
            time_cutoff: No new signals after this time (local).
            flatten_at_session_end: Flatten all positions at session end.
        """
        self.max_signals_per_day = max_signals_per_day
        self.lockout_after_losses = lockout_after_losses
        self.max_daily_loss_r = max_daily_loss_r
        self.time_cutoff = time_cutoff
        self.flatten_at_session_end = flatten_at_session_end
        
        self.state = GovernanceState()
        
        logger.debug(
            f"Governance initialized: max_signals={max_signals_per_day}, "
            f"lockout_after={lockout_after_losses}, max_daily_loss={max_daily_loss_r}R, "
            f"cutoff={time_cutoff}"
        )
    
    def new_day_reset(self, date: datetime.date) -> None:
        """Reset governance state for new trading day.
        
        Clears daily counters but preserves consecutive loss count
        (unless explicitly reset).
        
        Args:
            date: New trading date.
        """
        logger.info(
            f"New day reset: {date} (prev: signals={self.state.day_signal_count}, "
            f"losses={self.state.consecutive_losses})"
        )
        
        self.state.current_date = date
        self.state.day_signal_count = 0
        self.state.daily_realized_r = 0.0
        self.state.lockout_active = False
        self.state.lockout_reason = None
        self.state.trade_outcomes = []
        
        # Note: consecutive_losses persists across days by design
        # Can be reset manually if needed
    
    def new_session_reset(self, date: datetime.date) -> None:
        """Reset governance state for new session (full reset).
        
        Clears all counters including consecutive losses.
        
        Args:
            date: New session date.
        """
        logger.info(f"New session reset: {date}")
        
        self.state.current_date = date
        self.state.day_signal_count = 0
        self.state.consecutive_losses = 0
        self.state.daily_realized_r = 0.0
        self.state.lockout_active = False
        self.state.lockout_reason = None
        self.state.trade_outcomes = []
    
    def register_signal_emitted(self, timestamp: datetime) -> None:
        """Register that a signal was emitted.
        
        Increments daily signal count and updates date if needed.
        
        Args:
            timestamp: Signal timestamp.
        """
        signal_date = timestamp.date()
        
        # Check if new day
        if self.state.current_date != signal_date:
            self.new_day_reset(signal_date)
        
        self.state.day_signal_count += 1
        
        logger.debug(
            f"Signal emitted: count={self.state.day_signal_count}/"
            f"{self.max_signals_per_day}"
        )
    
    def register_trade_outcome(
        self,
        win: bool,
        realized_r: float = 0.0,
        full_stop_loss: bool = False,
    ) -> None:
        """Register trade outcome and update governance state.
        
        Args:
            win: Whether trade was profitable.
            realized_r: Realized R for the trade.
            full_stop_loss: Whether trade was a full stop loss (not partial exit).
        """
        self.state.trade_outcomes.append(win)
        
        # Update daily realized R
        self.state.daily_realized_r += realized_r
        
        logger.debug(
            f"Trade outcome registered: {'WIN' if win else 'LOSS'}, "
            f"R={realized_r:.2f}, daily_total={self.state.daily_realized_r:.2f}R"
        )
        
        # Check daily loss cap
        if self.max_daily_loss_r is not None:
            if self.state.daily_realized_r <= -self.max_daily_loss_r:
                self._activate_lockout(
                    f"Daily loss cap reached: {self.state.daily_realized_r:.2f}R "
                    f"<= -{self.max_daily_loss_r:.2f}R"
                )
                return  # Early exit, already locked out
        
        if win:
            # Reset consecutive losses on win
            self.state.consecutive_losses = 0
            logger.debug("Consecutive losses reset")
        
        elif full_stop_loss:
            # Increment consecutive losses on full stop
            self.state.consecutive_losses += 1
            logger.warning(
                f"FULL STOP LOSS "
                f"(consecutive={self.state.consecutive_losses}/"
                f"{self.lockout_after_losses})"
            )
            
            # Check if lockout triggered
            if self.state.consecutive_losses >= self.lockout_after_losses:
                self._activate_lockout(
                    f"Consecutive losses: {self.state.consecutive_losses}"
                )
        
        else:
            # Loss but not full stop (e.g., partial then stop)
            logger.debug("LOSS (not full stop, no consecutive loss penalty)")
    
    def can_emit_signal(
        self,
        current_time: datetime,
        check_date: bool = True,
    ) -> bool:
        """Check if signal can be emitted.
        
        Checks:
        1. Not locked out
        2. Daily signal cap not reached
        3. Before time cutoff (if set)
        4. Current date matches (if check_date)
        
        Args:
            current_time: Current timestamp.
            check_date: Whether to check date matches state.
            
        Returns:
            True if signal can be emitted.
        """
        current_date = current_time.date()
        current_time_only = current_time.time()
        
        # Check date (auto-reset if new day)
        if check_date and self.state.current_date != current_date:
            self.new_day_reset(current_date)
        
        # Check lockout
        if self.state.lockout_active:
            logger.debug(f"Signal blocked: {self.state.lockout_reason}")
            return False
        
        # Check daily cap
        if self.state.day_signal_count >= self.max_signals_per_day:
            logger.debug(
                f"Signal blocked: daily cap reached "
                f"({self.state.day_signal_count}/{self.max_signals_per_day})"
            )
            return False
        
        # Check time cutoff
        if self.time_cutoff is not None and current_time_only >= self.time_cutoff:
            logger.debug(f"Signal blocked: after cutoff time {self.time_cutoff}")
            return False
        
        return True
    
    def should_flatten_positions(self, current_time: datetime) -> bool:
        """Check if all positions should be flattened.
        
        Args:
            current_time: Current timestamp.
            
        Returns:
            True if positions should be closed.
        """
        if not self.flatten_at_session_end:
            return False
        
        # Check if near session end (implementation depends on session times)
        # For now, return False (caller should implement session-specific logic)
        return False
    
    def _activate_lockout(self, reason: str) -> None:
        """Activate trading lockout.
        
        Args:
            reason: Lockout reason.
        """
        self.state.lockout_active = True
        self.state.lockout_reason = reason
        
        logger.warning(f"LOCKOUT ACTIVATED: {reason}")
    
    def reset_consecutive_losses(self) -> None:
        """Manually reset consecutive losses counter.
        
        Useful for starting fresh on a new session or after review.
        """
        old_count = self.state.consecutive_losses
        self.state.consecutive_losses = 0
        
        if self.state.lockout_active and old_count >= self.lockout_after_losses:
            # Clear lockout if it was due to losses
            self.state.lockout_active = False
            self.state.lockout_reason = None
            logger.info("Consecutive losses reset, lockout cleared")
        else:
            logger.info(f"Consecutive losses reset: {old_count} → 0")
    
    def get_stats(self) -> dict:
        """Get governance statistics.
        
        Returns:
            Dictionary with governance metrics.
        """
        total_trades = len(self.state.trade_outcomes)
        wins = sum(self.state.trade_outcomes) if total_trades > 0 else 0
        
        return {
            'current_date': self.state.current_date,
            'day_signal_count': self.state.day_signal_count,
            'consecutive_losses': self.state.consecutive_losses,
            'daily_realized_r': self.state.daily_realized_r,
            'lockout_active': self.state.lockout_active,
            'lockout_reason': self.state.lockout_reason,
            'total_trades_today': total_trades,
            'wins_today': wins,
            'losses_today': total_trades - wins,
        }