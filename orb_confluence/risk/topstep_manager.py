"""TopStep-Compliant Risk Management

Phase 2 Enhancement #5: TopStep Combine risk controls.

Key Requirements (TopStep Combine Rules):
- Daily Loss Limit: -$1,000 max per day
- Trailing Drawdown: -$2,000 max from peak balance
- Must respect these limits to pass Combine and get funded account

Additional Conservative Limits:
- Weekly Loss Limit: -$1,500 (more conservative than required)
- Position Size Scaling: Reduce size as approaching limits
- Circuit Breakers: Automatic trading halt on breach

This is CRITICAL for live trading - violating TopStep rules = account failure.
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Dict, Any
from loguru import logger


@dataclass
class RiskLimits:
    """TopStep risk limit configuration.
    
    Attributes:
        daily_loss_limit: Maximum daily loss (negative value)
        trailing_drawdown_limit: Maximum drawdown from peak (negative value)
        weekly_loss_limit: Maximum weekly loss (negative value)
        max_position_size: Maximum contracts per position
    """
    daily_loss_limit: float
    trailing_drawdown_limit: float
    weekly_loss_limit: float
    max_position_size: int


@dataclass
class RiskStatus:
    """Current risk status.
    
    Attributes:
        can_trade: Whether trading is allowed
        reason: Reason for current status
        daily_pnl: Current daily PNL
        weekly_pnl: Current weekly PNL
        trailing_drawdown: Current drawdown from peak
        max_position_size: Current max position size allowed
        daily_limit_pct: Percentage of daily limit used
        weekly_limit_pct: Percentage of weekly limit used
        drawdown_limit_pct: Percentage of drawdown limit used
    """
    can_trade: bool
    reason: str
    daily_pnl: float
    weekly_pnl: float
    trailing_drawdown: float
    max_position_size: int
    daily_limit_pct: float
    weekly_limit_pct: float
    drawdown_limit_pct: float


class TopStepRiskManager:
    """TopStep-compliant risk management system.
    
    Enforces TopStep Combine rules and additional conservative limits:
    - Daily Loss Limit: -$1,000 (hard stop)
    - Trailing Drawdown: -$2,000 from peak balance (hard stop)
    - Weekly Loss Limit: -$1,500 (conservative, not required by TopStep)
    - Position Size Scaling: Automatic reduction near limits
    
    Circuit Breaker Behavior:
    - At 50% of limit: Reduce position size to 75%
    - At 70% of limit: Reduce position size to 50%
    - At 85% of limit: Reduce position size to 25%
    - At 100% of limit: STOP TRADING
    
    Example:
        >>> manager = TopStepRiskManager(account_size=100000, is_combine=True)
        >>> manager.update_equity(trade_pnl=-300)  # Lost $300
        >>> status = manager.check_risk_status()
        >>> if status.can_trade:
        ...     size = manager.get_position_size_limit(base_size=10)
        ...     # Trade with adjusted size
    """
    
    def __init__(
        self,
        account_size: float = 100000,
        is_combine: bool = True,
        enable_weekly_limit: bool = True,
        enable_position_scaling: bool = True,
    ):
        """Initialize TopStep risk manager.
        
        Args:
            account_size: Initial account size
            is_combine: True for Combine (stricter limits), False for funded
            enable_weekly_limit: Enable weekly loss limit (conservative)
            enable_position_scaling: Enable automatic position size scaling
        """
        # TopStep limits (Combine phase)
        if is_combine:
            self.limits = RiskLimits(
                daily_loss_limit=-1000.0,        # TopStep rule
                trailing_drawdown_limit=-2000.0,  # TopStep rule
                weekly_loss_limit=-1500.0,        # Conservative (not required)
                max_position_size=3,              # TopStep rule (3 contracts max)
            )
        else:
            # Funded account (more relaxed)
            self.limits = RiskLimits(
                daily_loss_limit=-2000.0,
                trailing_drawdown_limit=-3000.0,
                weekly_loss_limit=-3000.0,
                max_position_size=5,
            )
        
        # Configuration
        self.enable_weekly_limit = enable_weekly_limit
        self.enable_position_scaling = enable_position_scaling
        
        # Account tracking
        self.account_size = account_size
        self.current_equity = account_size
        self.peak_equity = account_size
        
        # Daily tracking
        self.daily_pnl = 0.0
        self.current_date = None
        
        # Weekly tracking
        self.weekly_pnl = 0.0
        self.week_start_equity = account_size
        self.current_week = None
        
        # Status
        self.trading_halted = False
        self.halt_reason = None
        
        logger.info(
            f"TopStepRiskManager initialized: "
            f"Combine={is_combine}, "
            f"Daily={self.limits.daily_loss_limit}, "
            f"DD={self.limits.trailing_drawdown_limit}, "
            f"Weekly={self.limits.weekly_loss_limit}, "
            f"MaxSize={self.limits.max_position_size}"
        )
    
    def update_equity(self, trade_pnl: float, timestamp: Optional[datetime] = None):
        """Update equity after a trade.
        
        Args:
            trade_pnl: Profit/loss from trade
            timestamp: Trade timestamp (for date/week tracking)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        trade_date = timestamp.date()
        
        # Check if new day
        if self.current_date is None or trade_date != self.current_date:
            self._reset_daily(trade_date)
        
        # Check if new week
        week_number = timestamp.isocalendar()[1]
        if self.current_week is None or week_number != self.current_week:
            self._reset_weekly(week_number, self.current_equity)
        
        # Update metrics
        self.daily_pnl += trade_pnl
        self.weekly_pnl += trade_pnl
        self.current_equity += trade_pnl
        
        # Update peak equity
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
            logger.debug(f"New peak equity: ${self.peak_equity:,.2f}")
        
        # Check limits
        self._check_limits()
    
    def _reset_daily(self, new_date: date):
        """Reset daily metrics for new trading day.
        
        Args:
            new_date: New trading date
        """
        if self.current_date is not None:
            logger.info(
                f"Day end: {self.current_date}, "
                f"Daily PNL: ${self.daily_pnl:,.2f}, "
                f"Equity: ${self.current_equity:,.2f}"
            )
        
        self.daily_pnl = 0.0
        self.current_date = new_date
        
        # Reset halt if it was daily-related
        if self.trading_halted and self.halt_reason == "DAILY_LOSS_LIMIT":
            self.trading_halted = False
            self.halt_reason = None
            logger.info("Trading resumed for new day")
    
    def _reset_weekly(self, new_week: int, current_equity: float):
        """Reset weekly metrics for new trading week.
        
        Args:
            new_week: New week number
            current_equity: Current account equity
        """
        if self.current_week is not None:
            logger.info(
                f"Week {self.current_week} end: "
                f"Weekly PNL: ${self.weekly_pnl:,.2f}, "
                f"Equity: ${current_equity:,.2f}"
            )
        
        self.weekly_pnl = 0.0
        self.week_start_equity = current_equity
        self.current_week = new_week
        
        # Reset halt if it was weekly-related
        if self.trading_halted and self.halt_reason == "WEEKLY_LOSS_LIMIT":
            self.trading_halted = False
            self.halt_reason = None
            logger.info("Trading resumed for new week")
    
    def _check_limits(self):
        """Check if any risk limits have been breached."""
        # Check daily loss limit
        if self.daily_pnl <= self.limits.daily_loss_limit:
            if not self.trading_halted:
                self.trading_halted = True
                self.halt_reason = "DAILY_LOSS_LIMIT"
                logger.error(
                    f"🛑 DAILY LOSS LIMIT BREACHED: "
                    f"${self.daily_pnl:,.2f} <= ${self.limits.daily_loss_limit:,.2f}"
                )
        
        # Check weekly loss limit
        if self.enable_weekly_limit and self.weekly_pnl <= self.limits.weekly_loss_limit:
            if not self.trading_halted:
                self.trading_halted = True
                self.halt_reason = "WEEKLY_LOSS_LIMIT"
                logger.error(
                    f"🛑 WEEKLY LOSS LIMIT BREACHED: "
                    f"${self.weekly_pnl:,.2f} <= ${self.limits.weekly_loss_limit:,.2f}"
                )
        
        # Check trailing drawdown
        trailing_dd = self.current_equity - self.peak_equity
        if trailing_dd <= self.limits.trailing_drawdown_limit:
            if not self.trading_halted:
                self.trading_halted = True
                self.halt_reason = "TRAILING_DRAWDOWN_LIMIT"
                logger.error(
                    f"🛑 TRAILING DRAWDOWN LIMIT BREACHED: "
                    f"${trailing_dd:,.2f} <= ${self.limits.trailing_drawdown_limit:,.2f}"
                )
    
    def check_risk_status(self) -> RiskStatus:
        """Check current risk status.
        
        Returns:
            RiskStatus with current state and limits
        """
        # Calculate percentages
        daily_limit_pct = (self.daily_pnl / self.limits.daily_loss_limit * 100) if self.limits.daily_loss_limit != 0 else 0
        weekly_limit_pct = (self.weekly_pnl / self.limits.weekly_loss_limit * 100) if self.limits.weekly_loss_limit != 0 else 0
        
        trailing_dd = self.current_equity - self.peak_equity
        drawdown_limit_pct = (trailing_dd / self.limits.trailing_drawdown_limit * 100) if self.limits.trailing_drawdown_limit != 0 else 0
        
        # Determine status
        if self.trading_halted:
            can_trade = False
            reason = f"Trading halted: {self.halt_reason}"
        else:
            can_trade = True
            
            # Provide warning if approaching limits
            if daily_limit_pct >= 70:
                reason = f"⚠️ Warning: {daily_limit_pct:.0f}% of daily limit used"
            elif weekly_limit_pct >= 70:
                reason = f"⚠️ Warning: {weekly_limit_pct:.0f}% of weekly limit used"
            elif drawdown_limit_pct >= 70:
                reason = f"⚠️ Warning: {drawdown_limit_pct:.0f}% of drawdown limit used"
            else:
                reason = "Within limits"
        
        # Get max position size
        max_size = self.get_position_size_limit(self.limits.max_position_size)
        
        return RiskStatus(
            can_trade=can_trade,
            reason=reason,
            daily_pnl=self.daily_pnl,
            weekly_pnl=self.weekly_pnl,
            trailing_drawdown=trailing_dd,
            max_position_size=max_size,
            daily_limit_pct=daily_limit_pct,
            weekly_limit_pct=weekly_limit_pct,
            drawdown_limit_pct=drawdown_limit_pct,
        )
    
    def get_position_size_limit(self, base_size: int) -> int:
        """Get position size limit based on current risk status.
        
        Implements circuit breaker logic:
        - < 50% of limit: Full size
        - 50-70% of limit: 75% size
        - 70-85% of limit: 50% size
        - 85-100% of limit: 25% size
        - >= 100%: No trading (0 size)
        
        Args:
            base_size: Base position size (contracts)
            
        Returns:
            Adjusted position size (contracts)
        """
        if self.trading_halted:
            return 0
        
        if not self.enable_position_scaling:
            return min(base_size, self.limits.max_position_size)
        
        # Calculate worst percentage across all limits
        daily_pct = abs(self.daily_pnl / self.limits.daily_loss_limit * 100) if self.limits.daily_loss_limit != 0 else 0
        weekly_pct = abs(self.weekly_pnl / self.limits.weekly_loss_limit * 100) if self.limits.weekly_loss_limit != 0 else 0
        
        trailing_dd = self.current_equity - self.peak_equity
        dd_pct = abs(trailing_dd / self.limits.trailing_drawdown_limit * 100) if self.limits.trailing_drawdown_limit != 0 else 0
        
        worst_pct = max(daily_pct, weekly_pct, dd_pct)
        
        # Apply circuit breaker
        if worst_pct >= 85:
            multiplier = 0.25  # 25% size
        elif worst_pct >= 70:
            multiplier = 0.50  # 50% size
        elif worst_pct >= 50:
            multiplier = 0.75  # 75% size
        else:
            multiplier = 1.0   # Full size
        
        adjusted_size = int(base_size * multiplier)
        
        # Apply max size limit
        adjusted_size = min(adjusted_size, self.limits.max_position_size)
        
        # Log if adjusted
        if adjusted_size < base_size:
            logger.info(
                f"Position size reduced: {base_size} → {adjusted_size} contracts "
                f"(worst limit usage: {worst_pct:.0f}%)"
            )
        
        return adjusted_size
    
    def reset_for_testing(self):
        """Reset manager state (for testing purposes only).
        
        WARNING: Never use this in production!
        """
        logger.warning("⚠️ Risk manager state reset (testing only!)")
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.current_equity = self.account_size
        self.peak_equity = self.account_size
        self.trading_halted = False
        self.halt_reason = None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get risk manager statistics.
        
        Returns:
            Dictionary with current state and configuration
        """
        trailing_dd = self.current_equity - self.peak_equity
        
        return {
            'limits': {
                'daily_loss_limit': self.limits.daily_loss_limit,
                'trailing_drawdown_limit': self.limits.trailing_drawdown_limit,
                'weekly_loss_limit': self.limits.weekly_loss_limit,
                'max_position_size': self.limits.max_position_size,
            },
            'current_state': {
                'account_size': self.account_size,
                'current_equity': self.current_equity,
                'peak_equity': self.peak_equity,
                'daily_pnl': self.daily_pnl,
                'weekly_pnl': self.weekly_pnl,
                'trailing_drawdown': trailing_dd,
                'trading_halted': self.trading_halted,
                'halt_reason': self.halt_reason,
            },
            'configuration': {
                'enable_weekly_limit': self.enable_weekly_limit,
                'enable_position_scaling': self.enable_position_scaling,
            }
        }





