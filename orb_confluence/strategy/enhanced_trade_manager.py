"""Enhanced trade manager with time stops, staged targets, and MFE/MAE tracking."""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import numpy as np
from loguru import logger


class ExitReason(str, Enum):
    """Trade exit reasons."""
    STOP_HIT = "STOP_HIT"
    TARGET1_HIT = "TARGET1_HIT"
    TARGET2_HIT = "TARGET2_HIT"
    RUNNER_HIT = "RUNNER_HIT"
    TIME_STOP = "TIME_STOP"
    BREAKEVEN_STOP = "BREAKEVEN_STOP"
    EOD = "EOD"
    TRAILING_STOP = "TRAILING_STOP"


@dataclass
class Target:
    """Profit target definition."""
    r_multiple: float
    price: float
    size_fraction: float  # Fraction of position (0.4 = 40%)
    hit: bool = False
    hit_timestamp: Optional[datetime] = None


@dataclass
class ActiveTrade:
    """Active trade with full state tracking."""
    trade_id: str
    instrument: str
    direction: str  # 'LONG' or 'SHORT'
    entry_timestamp: datetime
    entry_price: float
    position_size: int  # Number of contracts
    
    # Stop management
    initial_stop_price: float
    current_stop_price: float
    moved_to_breakeven: bool = False
    breakeven_timestamp: Optional[datetime] = None
    
    # Targets
    targets: List[Target] = field(default_factory=list)
    remaining_size: float = 1.0  # Fraction remaining (1.0 = 100%)
    
    # MFE/MAE tracking
    max_favorable_excursion: float = 0.0  # Best R reached
    max_adverse_excursion: float = 0.0   # Worst R reached
    mfe_timestamp: Optional[datetime] = None
    mae_timestamp: Optional[datetime] = None
    
    # Time stop
    time_stop_active: bool = True
    time_stop_deadline: Optional[datetime] = None
    min_progress_r_required: float = 0.4
    
    # Performance tracking
    bars_held: int = 0
    reached_1r: bool = False
    time_to_1r: Optional[float] = None  # Minutes


class EnhancedTradeManager:
    """Manage active trade with staged targets, time stops, and breakeven logic."""
    
    def __init__(self, instrument_config):
        """Initialize trade manager.
        
        Args:
            instrument_config: InstrumentConfig with target and stop settings
        """
        self.config = instrument_config
    
    def create_trade(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_timestamp: datetime,
        entry_price: float,
        stop_price: float,
        position_size: int
    ) -> ActiveTrade:
        """Create a new active trade with targets.
        
        Args:
            trade_id: Unique trade identifier
            instrument: Symbol
            direction: 'LONG' or 'SHORT'
            entry_timestamp: Entry time
            entry_price: Entry price
            stop_price: Initial stop loss price
            position_size: Number of contracts
        
        Returns:
            ActiveTrade object
        """
        # Calculate R (risk per contract)
        if direction == 'LONG':
            risk_per_contract = entry_price - stop_price
        else:  # SHORT
            risk_per_contract = stop_price - entry_price
        
        if risk_per_contract <= 0:
            raise ValueError(f"Invalid stop: risk_per_contract = {risk_per_contract}")
        
        # Build targets
        targets = self._build_targets(entry_price, risk_per_contract, direction)
        
        # Time stop deadline
        time_stop_deadline = entry_timestamp + timedelta(
            minutes=self.config.time_stop_minutes
        ) if self.config.time_stop_enabled else None
        
        trade = ActiveTrade(
            trade_id=trade_id,
            instrument=instrument,
            direction=direction,
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            position_size=position_size,
            initial_stop_price=stop_price,
            current_stop_price=stop_price,
            targets=targets,
            time_stop_deadline=time_stop_deadline,
            min_progress_r_required=self.config.time_stop_min_progress_r
        )
        
        logger.info(
            f"Trade created: {trade_id} {direction} @ {entry_price:.2f}, "
            f"stop={stop_price:.2f}, risk={risk_per_contract:.2f}, "
            f"targets={len(targets)}"
        )
        
        return trade
    
    def _build_targets(
        self,
        entry_price: float,
        risk: float,
        direction: str
    ) -> List[Target]:
        """Build staged profit targets.
        
        Args:
            entry_price: Entry price
            risk: Risk per contract (R)
            direction: 'LONG' or 'SHORT'
        
        Returns:
            List of Target objects
        """
        targets = []
        
        # T1: First target
        t1_r = self.config.target_t1_r
        if direction == 'LONG':
            t1_price = entry_price + (risk * t1_r)
        else:
            t1_price = entry_price - (risk * t1_r)
        
        targets.append(Target(
            r_multiple=t1_r,
            price=t1_price,
            size_fraction=self.config.target_t1_fraction
        ))
        
        # T2: Second target
        t2_r = self.config.target_t2_r
        if direction == 'LONG':
            t2_price = entry_price + (risk * t2_r)
        else:
            t2_price = entry_price - (risk * t2_r)
        
        targets.append(Target(
            r_multiple=t2_r,
            price=t2_price,
            size_fraction=self.config.target_t2_fraction
        ))
        
        # Runner: Final target
        runner_r = self.config.target_runner_r
        if direction == 'LONG':
            runner_price = entry_price + (risk * runner_r)
        else:
            runner_price = entry_price - (risk * runner_r)
        
        # Remaining size after T1 and T2
        runner_fraction = 1.0 - self.config.target_t1_fraction - self.config.target_t2_fraction
        
        targets.append(Target(
            r_multiple=runner_r,
            price=runner_price,
            size_fraction=runner_fraction
        ))
        
        return targets
    
    def update(
        self,
        trade: ActiveTrade,
        current_timestamp: datetime,
        current_price: float,
        bar_high: float,
        bar_low: float
    ) -> Tuple[ActiveTrade, List[dict]]:
        """Update trade state and check for exits.
        
        Args:
            trade: ActiveTrade object
            current_timestamp: Current bar timestamp
            current_price: Current close price
            bar_high: Bar high (for stops/targets)
            bar_low: Bar low (for stops/targets)
        
        Returns:
            Tuple of (updated_trade, list_of_exit_events)
        """
        trade.bars_held += 1
        
        # Calculate current R
        if trade.direction == 'LONG':
            risk = trade.entry_price - trade.initial_stop_price
            current_r = (current_price - trade.entry_price) / risk if risk > 0 else 0.0
        else:  # SHORT
            risk = trade.initial_stop_price - trade.entry_price
            current_r = (trade.entry_price - current_price) / risk if risk > 0 else 0.0
        
        # Update MFE/MAE
        if current_r > trade.max_favorable_excursion:
            trade.max_favorable_excursion = current_r
            trade.mfe_timestamp = current_timestamp
            
            # Check if reached +1R for first time
            if not trade.reached_1r and current_r >= 1.0:
                trade.reached_1r = True
                minutes_elapsed = (current_timestamp - trade.entry_timestamp).total_seconds() / 60
                trade.time_to_1r = minutes_elapsed
                logger.info(f"{trade.trade_id}: Reached +1R in {minutes_elapsed:.1f} minutes")
        
        if current_r < trade.max_adverse_excursion:
            trade.max_adverse_excursion = current_r
            trade.mae_timestamp = current_timestamp
        
        # Move to breakeven at +0.4R (OPTIMIZED for ES via 20-trial search)
        if not trade.moved_to_breakeven and current_r >= 0.4:
            trade.current_stop_price = trade.entry_price
            trade.moved_to_breakeven = True
            trade.breakeven_timestamp = current_timestamp
            logger.info(f"{trade.trade_id}: Stop moved to breakeven at +{current_r:.2f}R")
        
        # Check for exits (order matters: stop first, then targets)
        exit_events = []
        
        # 1. Check stop loss
        if trade.direction == 'LONG':
            if bar_low <= trade.current_stop_price:
                reason = ExitReason.BREAKEVEN_STOP if trade.moved_to_breakeven else ExitReason.STOP_HIT
                exit_events.append({
                    'reason': reason,
                    'timestamp': current_timestamp,
                    'price': trade.current_stop_price,
                    'size_fraction': trade.remaining_size,
                    'r_multiple': current_r
                })
                return trade, exit_events
        else:  # SHORT
            if bar_high >= trade.current_stop_price:
                reason = ExitReason.BREAKEVEN_STOP if trade.moved_to_breakeven else ExitReason.STOP_HIT
                exit_events.append({
                    'reason': reason,
                    'timestamp': current_timestamp,
                    'price': trade.current_stop_price,
                    'size_fraction': trade.remaining_size,
                    'r_multiple': current_r
                })
                return trade, exit_events
        
        # 2. Check targets (in order)
        for target in trade.targets:
            if target.hit:
                continue  # Already hit
            
            hit = False
            if trade.direction == 'LONG':
                hit = bar_high >= target.price
            else:  # SHORT
                hit = bar_low <= target.price
            
            if hit:
                target.hit = True
                target.hit_timestamp = current_timestamp
                trade.remaining_size -= target.size_fraction
                
                exit_events.append({
                    'reason': self._target_to_exit_reason(target),
                    'timestamp': current_timestamp,
                    'price': target.price,
                    'size_fraction': target.size_fraction,
                    'r_multiple': target.r_multiple
                })
                
                logger.info(
                    f"{trade.trade_id}: Target hit at {target.r_multiple:.1f}R, "
                    f"remaining={trade.remaining_size:.1%}"
                )
                
                # Breakeven now handled proactively at +0.5R (see above)
                
                # If all targets hit, we're done
                if trade.remaining_size <= 0.01:  # Close enough to zero
                    return trade, exit_events
        
        # 3. Check time stop
        if (trade.time_stop_active and 
            trade.time_stop_deadline and 
            current_timestamp >= trade.time_stop_deadline):
            
            if current_r < trade.min_progress_r_required:
                # Time stop triggered
                exit_events.append({
                    'reason': ExitReason.TIME_STOP,
                    'timestamp': current_timestamp,
                    'price': current_price,
                    'size_fraction': trade.remaining_size,
                    'r_multiple': current_r
                })
                logger.warning(
                    f"{trade.trade_id}: TIME STOP - insufficient progress "
                    f"({current_r:.2f}R < {trade.min_progress_r_required:.2f}R required)"
                )
                return trade, exit_events
            else:
                # Disable time stop - trade has shown progress
                trade.time_stop_active = False
                logger.info(f"{trade.trade_id}: Time stop cleared (progress made)")
        
        return trade, exit_events
    
    def _target_to_exit_reason(self, target: Target) -> ExitReason:
        """Map target to exit reason."""
        if target.r_multiple <= 1.0:
            return ExitReason.TARGET1_HIT
        elif target.r_multiple <= 2.0:
            return ExitReason.TARGET2_HIT
        else:
            return ExitReason.RUNNER_HIT
    
    def force_exit_eod(
        self,
        trade: ActiveTrade,
        timestamp: datetime,
        price: float
    ) -> List[dict]:
        """Force exit at end of day.
        
        Args:
            trade: ActiveTrade to exit
            timestamp: Exit timestamp
            price: Exit price
        
        Returns:
            List with single EOD exit event
        """
        # Calculate final R
        if trade.direction == 'LONG':
            risk = trade.entry_price - trade.initial_stop_price
            final_r = (price - trade.entry_price) / risk if risk > 0 else 0.0
        else:
            risk = trade.initial_stop_price - trade.entry_price
            final_r = (trade.entry_price - price) / risk if risk > 0 else 0.0
        
        exit_event = {
            'reason': ExitReason.EOD,
            'timestamp': timestamp,
            'price': price,
            'size_fraction': trade.remaining_size,
            'r_multiple': final_r
        }
        
        logger.info(f"{trade.trade_id}: EOD exit at {price:.2f} ({final_r:+.2f}R)")
        
        return [exit_event]
