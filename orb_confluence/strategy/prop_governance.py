"""Daily governance engine for prop firm evaluation compliance.

Enforces:
- Daily loss limits
- Trailing drawdown limits
- Profit target pacing
- Trade concurrency limits
- Consecutive loss lockouts
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from datetime import datetime, date
from loguru import logger


@dataclass
class PropAccountRules:
    """Prop firm account rules and limits."""
    account_size: float
    profit_target: float
    trailing_drawdown_max: float
    daily_loss_limit: float
    max_contracts: int = 3
    max_concurrent_trades: int = 2
    consecutive_loss_lockout: int = 3  # Lockout after N losses in a row
    
    def __post_init__(self):
        """Validate rules."""
        assert self.profit_target > 0
        assert self.trailing_drawdown_max > 0
        assert self.daily_loss_limit > 0
        assert self.daily_loss_limit <= self.trailing_drawdown_max


@dataclass
class PacingPhase:
    """Capital pacing phase definition."""
    name: str
    profit_pct_min: float  # Min % of profit target to enter phase
    profit_pct_max: float  # Max % of profit target for phase
    size_multiplier: float  # Multiplier on baseline size
    daily_loss_pct: float  # % of daily loss limit allowed
    description: str


class PropGovernanceEngine:
    """Enforce prop firm evaluation rules and capital pacing with per-instrument tracking."""
    
    # Pacing phases (% of profit target)
    PHASES = [
        PacingPhase("Conservative", 0.0, 0.40, 1.0, 1.0, "Build foundation"),
        PacingPhase("Growth", 0.40, 0.70, 1.5, 1.0, "Scale winners"),
        PacingPhase("Protection", 0.70, 1.0, 1.0, 0.6, "Protect gains"),
    ]
    
    def __init__(
        self,
        rules: PropAccountRules,
        instruments: List[str],
        max_daily_trades_per_instrument: int = 2,
        starting_balance: Optional[float] = None
    ):
        """Initialize governance engine with per-instrument tracking.
        
        Args:
            rules: PropAccountRules defining limits
            instruments: List of instruments to track
            max_daily_trades_per_instrument: Max trades per day per instrument
            starting_balance: Starting balance (defaults to account_size)
        """
        self.rules = rules
        self.starting_balance = starting_balance or rules.account_size
        self.instruments = instruments
        self.max_daily_trades_per_instrument = max_daily_trades_per_instrument
        
        # Current state
        self.current_balance = self.starting_balance
        self.peak_balance = self.starting_balance
        self.total_profit = 0.0
        
        # Daily tracking (global)
        self.current_date: Optional[date] = None
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.daily_r_total = 0.0
        
        # Per-instrument tracking
        self.instrument_daily_trades: Dict[str, int] = {inst: 0 for inst in instruments}
        self.instrument_consecutive_losses: Dict[str, int] = {inst: 0 for inst in instruments}
        self.instrument_consecutive_wins: Dict[str, int] = {inst: 0 for inst in instruments}
        self.instrument_lockout: Dict[str, bool] = {inst: False for inst in instruments}
        
        # Active trades
        self.active_trade_count = 0
        self.correlated_exposure = 0.0  # Risk-weighted exposure
        
        # Global consecutive tracking (kept for legacy compatibility)
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        
        # Flags
        self.daily_halt = False
        self.trailing_dd_halt = False
        self.lockout_active = False  # Global lockout (now rarely used)
        
        logger.info(
            f"Governance initialized: ${rules.account_size:.0f} account, "
            f"${rules.profit_target:.0f} target, "
            f"${rules.daily_loss_limit:.0f} daily limit, "
            f"{len(instruments)} instruments, "
            f"max {max_daily_trades_per_instrument} trades/day per instrument"
        )
    
    def new_trading_day(self, trading_date: date):
        """Reset daily counters for new trading day."""
        if self.current_date != trading_date:
            self.current_date = trading_date
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.daily_r_total = 0.0
            self.daily_halt = False
            
            # Reset per-instrument daily trade counts
            for inst in self.instruments:
                self.instrument_daily_trades[inst] = 0
            
            logger.info(f"New trading day: {trading_date}, Phase: {self.get_current_phase().name}")
    
    def get_current_phase(self) -> PacingPhase:
        """Get current pacing phase based on profit progress."""
        profit_pct = self.total_profit / self.rules.profit_target
        
        for phase in self.PHASES:
            if phase.profit_pct_min <= profit_pct < phase.profit_pct_max:
                return phase
        
        # If beyond target, use protection phase
        return self.PHASES[-1]
    
    def can_take_trade(
        self,
        trade_risk_dollars: float,
        instrument: str,
        correlated_instruments: List[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if a trade can be taken with per-instrument tracking.
        
        Args:
            trade_risk_dollars: Dollar risk for this trade
            instrument: Symbol being traded
            correlated_instruments: List of correlated symbols already in trades
        
        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        # Check per-instrument daily trade limit
        if self.instrument_daily_trades.get(instrument, 0) >= self.max_daily_trades_per_instrument:
            return False, f"{instrument}_max_daily_trades_reached ({self.max_daily_trades_per_instrument})"
        
        # Check per-instrument lockout
        if self.instrument_lockout.get(instrument, False):
            losses = self.instrument_consecutive_losses.get(instrument, 0)
            return False, f"{instrument}_lockout_after_{losses}_losses"
        
        # Check daily halt (global)
        if self.daily_halt:
            return False, "daily_loss_limit_reached"
        
        # Check trailing drawdown halt (global) - DISABLED for initial data collection
        # if self.trailing_dd_halt:
        #     return False, "trailing_drawdown_limit_reached"
        
        # Check concurrent trade limit (global)
        if self.active_trade_count >= self.rules.max_concurrent_trades:
            return False, f"max_concurrent_trades_{self.rules.max_concurrent_trades}"
        
        # Check if adding this trade would exceed daily loss budget (global)
        phase = self.get_current_phase()
        daily_budget_remaining = (self.rules.daily_loss_limit * phase.daily_loss_pct) + self.daily_pnl
        
        if trade_risk_dollars > daily_budget_remaining:
            return False, f"would_exceed_daily_budget (${daily_budget_remaining:.0f} remaining)"
        
        # Check trailing drawdown budget (global) - DISABLED for initial data collection
        # current_dd = self.peak_balance - self.current_balance
        # dd_remaining = self.rules.trailing_drawdown_max - current_dd
        # 
        # if trade_risk_dollars > dd_remaining * 0.5:  # Don't risk more than 50% of remaining DD room
        #     return False, f"too_close_to_trailing_dd (${dd_remaining:.0f} remaining)"
        
        # All checks passed
        return True, None
    
    def register_trade_entry(
        self,
        trade_id: str,
        risk_dollars: float,
        instrument: str
    ):
        """Register a new trade entry with per-instrument tracking."""
        self.active_trade_count += 1
        self.daily_trade_count += 1
        
        # Track per-instrument
        self.instrument_daily_trades[instrument] = self.instrument_daily_trades.get(instrument, 0) + 1
        
        logger.info(
            f"Trade entered: {trade_id}, risk=${risk_dollars:.0f}, "
            f"active={self.active_trade_count}, daily={self.daily_trade_count}"
        )
    
    def register_trade_exit(
        self,
        trade_id: str,
        pnl_dollars: float,
        r_multiple: float,
        instrument: str
    ):
        """Register a trade exit and update governance state with per-instrument tracking.
        
        Args:
            trade_id: Trade identifier
            pnl_dollars: Profit/loss in dollars
            r_multiple: R-multiple (positive or negative)
            instrument: Symbol that was traded
        """
        # Update balances
        self.current_balance += pnl_dollars
        self.total_profit += pnl_dollars
        self.daily_pnl += pnl_dollars
        self.daily_r_total += r_multiple
        
        # Update peak for trailing drawdown
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        # Update active count
        self.active_trade_count = max(0, self.active_trade_count - 1)
        
        # Update global win/loss streaks (for legacy compatibility)
        if pnl_dollars > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        # Update per-instrument win/loss streaks
        if pnl_dollars > 0:
            self.instrument_consecutive_wins[instrument] = self.instrument_consecutive_wins.get(instrument, 0) + 1
            self.instrument_consecutive_losses[instrument] = 0
            self.instrument_lockout[instrument] = False  # Clear instrument lockout on win
        else:
            self.instrument_consecutive_losses[instrument] = self.instrument_consecutive_losses.get(instrument, 0) + 1
            self.instrument_consecutive_wins[instrument] = 0
            
            # Check for per-instrument lockout (disabled for now - user wants all instruments trading)
            # if self.instrument_consecutive_losses[instrument] >= self.rules.consecutive_loss_lockout:
            #     self.instrument_lockout[instrument] = True
            #     logger.warning(
            #         f"{instrument} LOCKOUT ACTIVATED after {self.instrument_consecutive_losses[instrument]} consecutive losses"
            #     )
        
        # Check daily loss limit
        if self.daily_pnl <= -self.rules.daily_loss_limit:
            self.daily_halt = True
            logger.error(
                f"DAILY HALT: loss ${abs(self.daily_pnl):.0f} >= "
                f"${self.rules.daily_loss_limit:.0f} limit"
            )
        
        # Check trailing drawdown
        current_dd = self.peak_balance - self.current_balance
        if current_dd >= self.rules.trailing_drawdown_max:
            self.trailing_dd_halt = True
            logger.error(
                f"TRAILING DD HALT: drawdown ${current_dd:.0f} >= "
                f"${self.rules.trailing_drawdown_max:.0f} limit"
            )
        
        # Check profit target reached
        if self.total_profit >= self.rules.profit_target:
            logger.success(
                f"🎯 PROFIT TARGET REACHED: ${self.total_profit:.0f} >= "
                f"${self.rules.profit_target:.0f}"
            )
        
        logger.info(
            f"{instrument} trade exited: {trade_id}, P/L=${pnl_dollars:+.0f} ({r_multiple:+.2f}R), "
            f"Balance=${self.current_balance:.0f}, "
            f"Daily: ${self.daily_pnl:+.0f} ({self.daily_trade_count} trades), "
            f"{instrument} daily: {self.instrument_daily_trades[instrument]}/{self.max_daily_trades_per_instrument}"
        )
    
    def get_position_size_multiplier(self) -> float:
        """Get position size multiplier based on current phase."""
        phase = self.get_current_phase()
        return phase.size_multiplier
    
    def get_status(self) -> Dict:
        """Get current governance status."""
        phase = self.get_current_phase()
        current_dd = self.peak_balance - self.current_balance
        profit_pct = (self.total_profit / self.rules.profit_target * 100) if self.rules.profit_target > 0 else 0
        
        return {
            'current_balance': self.current_balance,
            'peak_balance': self.peak_balance,
            'total_profit': self.total_profit,
            'profit_target_pct': profit_pct,
            'current_phase': phase.name,
            'phase_multiplier': phase.size_multiplier,
            'daily_pnl': self.daily_pnl,
            'daily_trade_count': self.daily_trade_count,
            'daily_r_total': self.daily_r_total,
            'active_trades': self.active_trade_count,
            'current_drawdown': current_dd,
            'dd_pct_of_max': (current_dd / self.rules.trailing_drawdown_max * 100),
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'daily_halt': self.daily_halt,
            'trailing_dd_halt': self.trailing_dd_halt,
            'lockout_active': self.lockout_active,
            'can_trade': not (self.daily_halt or self.trailing_dd_halt or self.lockout_active)
        }
    
    def reset_for_new_evaluation(self):
        """Reset for a new evaluation cycle."""
        self.current_balance = self.starting_balance
        self.peak_balance = self.starting_balance
        self.total_profit = 0.0
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.daily_r_total = 0.0
        self.active_trade_count = 0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.daily_halt = False
        self.trailing_dd_halt = False
        self.lockout_active = False
        
        logger.info("Governance reset for new evaluation cycle")


# Pre-configured Topstep-style account templates
TOPSTEP_50K = PropAccountRules(
    account_size=50_000,
    profit_target=3_000,
    trailing_drawdown_max=2_000,
    daily_loss_limit=1_000,
    max_contracts=3,
    max_concurrent_trades=2,
    consecutive_loss_lockout=3
)

TOPSTEP_100K = PropAccountRules(
    account_size=100_000,
    profit_target=6_000,
    trailing_drawdown_max=3_000,
    daily_loss_limit=2_000,
    max_contracts=5,
    max_concurrent_trades=2,
    consecutive_loss_lockout=3
)

TOPSTEP_150K = PropAccountRules(
    account_size=150_000,
    profit_target=9_000,
    trailing_drawdown_max=4_500,
    daily_loss_limit=3_000,
    max_contracts=7,
    max_concurrent_trades=3,
    consecutive_loss_lockout=3
)
