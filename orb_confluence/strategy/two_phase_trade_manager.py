"""Enhanced Trade Manager with 2-Phase Stop Logic.

Phase 2 Enhancement #1: Addresses win/loss asymmetry problem.

Key Features:
- Phase 1: Initial stop (entry to +0.3R) - tighter stops
- Phase 2: Breakeven (0.3R to 0.5R) - protect small wins
- Phase 3: Trailing stop (>0.5R) - capture larger moves

Expected Impact:
- Reduce avg loss from -0.52R to -0.35R (33% improvement)
- Protect small wins from turning into losses
- Improve win/loss ratio from 0.72x to ~1.0x
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional
import pandas as pd
from loguru import logger

from .trade_state import ActiveTrade, PartialFill
from .trade_manager import TradeEvent, TradeUpdate


class TwoPhaseTradeManager:
    """Enhanced trade manager with 2-phase stop logic.
    
    Implements 3-phase stop management:
    1. Initial Stop (entry → 0.3R profit): Tighter stop than before
    2. Breakeven (0.3R → 0.5R profit): Move to entry price
    3. Trailing (> 0.5R profit): Trail behind peak by fixed distance
    
    This addresses the win/loss asymmetry identified in Phase 1 analysis,
    where July losses were 39% larger than wins (0.72x ratio).
    
    Example:
        >>> manager = TwoPhaseTradeManager(
        ...     breakeven_threshold_r=0.3,
        ...     trailing_start_r=0.5,
        ...     trail_distance_r=0.3
        ... )
        >>> trade = ActiveTrade(...)
        >>> 
        >>> for bar in bars:
        ...     update = manager.update(trade, bar)
        ...     if update.closed:
        ...         break
    """
    
    def __init__(
        self,
        conservative_fills: bool = True,
        breakeven_threshold_r: float = 0.3,  # Move to BE at 0.3R (vs 1.0R before)
        trailing_start_r: float = 0.5,       # Start trailing at 0.5R
        trail_distance_r: float = 0.3,       # Trail 0.3R behind peak
        be_buffer: float = 0.0,              # Buffer when moving to BE
        enable_trailing: bool = True,        # Enable trailing stop logic
    ):
        """Initialize enhanced trade manager.
        
        Args:
            conservative_fills: If both stop and target hit in bar, assume stop first.
            breakeven_threshold_r: Move stop to breakeven after this R achieved.
            trailing_start_r: Start trailing stop after this R achieved.
            trail_distance_r: Trail this many R behind peak profit.
            be_buffer: Buffer (in price points) when moving to breakeven.
            enable_trailing: Enable trailing stop logic (Phase 3).
        """
        self.conservative_fills = conservative_fills
        self.breakeven_threshold_r = breakeven_threshold_r
        self.trailing_start_r = trailing_start_r
        self.trail_distance_r = trail_distance_r
        self.be_buffer = be_buffer
        self.enable_trailing = enable_trailing
        
        # Track trailing stop state
        self.trailing_active = {}  # trade_id -> bool
        self.peak_r = {}           # trade_id -> max R seen
        
        logger.info(
            f"TwoPhaseTradeManager initialized: BE@{breakeven_threshold_r:.2f}R, "
            f"Trail@{trailing_start_r:.2f}R, Distance={trail_distance_r:.2f}R"
        )
    
    def update(
        self,
        trade: ActiveTrade,
        bar: pd.Series,
    ) -> TradeUpdate:
        """Update trade with new bar using 2-phase stop logic.
        
        Args:
            trade: Active trade to update.
            bar: Current bar with timestamp_utc, open, high, low, close.
            
        Returns:
            TradeUpdate with modified trade, events, and closed flag.
            
        Process:
            1. Update R extremes (MFE/MAE tracking)
            2. Check for stop hit
            3. Check for target hits
            4. Update stop based on phase (initial/breakeven/trailing)
        """
        events = []
        
        if trade.is_closed:
            logger.warning(f"Attempted to update closed trade: {trade.trade_id}")
            return TradeUpdate(trade=trade, events=[], closed=True)
        
        # Extract bar data
        bar_high = bar['high']
        bar_low = bar['low']
        bar_timestamp = bar['timestamp_utc']
        
        # Update R extremes (for MFE/MAE tracking)
        trade.update_r_extremes(bar_high)
        trade.update_r_extremes(bar_low)
        
        # Update peak R for trailing logic
        current_r = self._calculate_current_r(trade, bar_high, bar_low)
        trade_id = trade.trade_id
        
        if trade_id not in self.peak_r:
            self.peak_r[trade_id] = current_r
        else:
            self.peak_r[trade_id] = max(self.peak_r[trade_id], current_r)
        
        # Apply 2-phase stop logic BEFORE checking for stop hit
        stop_update_events = self._update_stop_logic(trade, bar_high, bar_low)
        events.extend(stop_update_events)
        
        # Conservative fills: check if both stop and target hit
        stop_hit = self._check_stop_hit(trade, bar_high, bar_low)
        target_hit = self._check_any_target_hit(trade, bar_high, bar_low)
        
        if self.conservative_fills and stop_hit and target_hit:
            # Both hit: assume stop hit first (conservative)
            logger.debug(
                f"Conservative fill: stop and target both hit for {trade.trade_id}, "
                f"assuming stop first"
            )
            trade = self._close_on_stop(trade, bar_timestamp)
            events.append(TradeEvent.STOP_HIT)
            self._cleanup_trade_tracking(trade_id)
            return TradeUpdate(trade=trade, events=events, closed=True)
        
        # Check for stop hit
        if stop_hit:
            trade = self._close_on_stop(trade, bar_timestamp)
            events.append(TradeEvent.STOP_HIT)
            self._cleanup_trade_tracking(trade_id)
            return TradeUpdate(trade=trade, events=events, closed=True)
        
        # Check for partial fills
        partials_events = self._check_partial_fills(trade, bar_high, bar_low, bar_timestamp)
        events.extend(partials_events)
        
        # Check if all partials filled (trade complete)
        if trade.remaining_size <= 0.001:  # Floating point tolerance
            trade.exit_timestamp = bar_timestamp
            trade.exit_price = trade.partials_filled[-1].price
            trade.exit_reason = 'all_targets'
            trade.realized_r = self._compute_realized_r(trade)
            events.append(TradeEvent.TARGET_HIT)
            self._cleanup_trade_tracking(trade_id)
            return TradeUpdate(trade=trade, events=events, closed=True)
        
        return TradeUpdate(trade=trade, events=events, closed=False)
    
    def _update_stop_logic(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> List[TradeEvent]:
        """Update stop price based on 2-phase logic.
        
        Phase 1: Initial Stop (entry to 0.3R)
        - Use initial stop price set at entry
        
        Phase 2: Breakeven (0.3R to 0.5R)
        - Move stop to entry price (breakeven)
        - Protects small wins from turning into losses
        
        Phase 3: Trailing (> 0.5R)
        - Trail stop behind peak by trail_distance_r
        - Captures more of large winning moves
        
        Args:
            trade: Active trade (modified in place).
            bar_high: Bar high price.
            bar_low: Bar low price.
            
        Returns:
            List of events (BREAKEVEN_MOVE if stop was moved).
        """
        events = []
        trade_id = trade.trade_id
        
        # Calculate current profit in R
        current_r = self._calculate_current_r(trade, bar_high, bar_low)
        peak_r = self.peak_r.get(trade_id, current_r)
        
        # Phase 2: Move to Breakeven at 0.3R
        if not trade.moved_to_breakeven and current_r >= self.breakeven_threshold_r:
            old_stop = trade.stop_price_current
            
            if trade.direction == 'long':
                new_stop = trade.entry_price + self.be_buffer
            else:
                new_stop = trade.entry_price - self.be_buffer
            
            # Only move stop if it's better (don't move backward)
            if self._is_better_stop(trade, new_stop, old_stop):
                trade.stop_price_current = new_stop
                trade.moved_to_breakeven = True
                trade.breakeven_price = new_stop
                
                logger.info(
                    f"[2-Phase] BREAKEVEN: {trade.trade_id} stop moved {old_stop:.2f} → {new_stop:.2f} "
                    f"at {current_r:.2f}R (threshold: {self.breakeven_threshold_r:.2f}R)"
                )
                
                events.append(TradeEvent.BREAKEVEN_MOVE)
        
        # Phase 3: Trailing Stop at 0.5R+
        if self.enable_trailing and peak_r >= self.trailing_start_r:
            # Activate trailing if not already active
            if trade_id not in self.trailing_active or not self.trailing_active[trade_id]:
                self.trailing_active[trade_id] = True
                logger.info(
                    f"[2-Phase] TRAILING ACTIVATED: {trade.trade_id} at {peak_r:.2f}R "
                    f"(threshold: {self.trailing_start_r:.2f}R)"
                )
            
            # Calculate trailing stop based on peak R
            trail_r = peak_r - self.trail_distance_r
            
            # Convert trail_r to price
            new_trail_stop = self._calculate_stop_from_r(trade, trail_r)
            
            old_stop = trade.stop_price_current
            
            # Only move stop if it's better (tighter)
            if self._is_better_stop(trade, new_trail_stop, old_stop):
                trade.stop_price_current = new_trail_stop
                
                logger.debug(
                    f"[2-Phase] TRAIL UPDATE: {trade.trade_id} stop {old_stop:.2f} → {new_trail_stop:.2f} "
                    f"(peak: {peak_r:.2f}R, trail: {trail_r:.2f}R)"
                )
        
        return events
    
    def _calculate_current_r(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> float:
        """Calculate current R using most favorable price in bar.
        
        Args:
            trade: Active trade.
            bar_high: Bar high price.
            bar_low: Bar low price.
            
        Returns:
            Current R-multiple.
        """
        # Use most favorable price
        if trade.direction == 'long':
            favorable_price = bar_high
        else:
            favorable_price = bar_low
        
        return trade.compute_current_r(favorable_price)
    
    def _calculate_stop_from_r(
        self,
        trade: ActiveTrade,
        target_r: float,
    ) -> float:
        """Calculate stop price for a given R-multiple.
        
        Args:
            trade: Active trade.
            target_r: Target R-multiple for stop.
            
        Returns:
            Stop price.
        """
        # R = (price - entry) / initial_risk (for long)
        # price = entry + (R * initial_risk)
        
        initial_risk = abs(trade.entry_price - trade.stop_price_initial)
        
        if trade.direction == 'long':
            # For long: stop below entry
            # If target_r is positive, stop is entry + positive offset
            # If target_r is negative, stop is entry + negative offset (below entry)
            stop_price = trade.entry_price + (target_r * initial_risk)
        else:
            # For short: stop above entry
            stop_price = trade.entry_price - (target_r * initial_risk)
        
        return stop_price
    
    def _is_better_stop(
        self,
        trade: ActiveTrade,
        new_stop: float,
        old_stop: float,
    ) -> bool:
        """Check if new stop is better (tighter) than old stop.
        
        Args:
            trade: Active trade.
            new_stop: Proposed new stop price.
            old_stop: Current stop price.
            
        Returns:
            True if new stop is better (tighter).
        """
        if trade.direction == 'long':
            # For long, better stop is higher (tighter)
            return new_stop > old_stop
        else:
            # For short, better stop is lower (tighter)
            return new_stop < old_stop
    
    def _cleanup_trade_tracking(self, trade_id: str):
        """Clean up tracking dictionaries for closed trade.
        
        Args:
            trade_id: ID of closed trade.
        """
        self.trailing_active.pop(trade_id, None)
        self.peak_r.pop(trade_id, None)
    
    # =========================================================================
    # Methods from base TradeManager (with minimal changes)
    # =========================================================================
    
    def _check_stop_hit(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> bool:
        """Check if stop was hit in bar."""
        if trade.direction == 'long':
            return bar_low <= trade.stop_price_current
        else:
            return bar_high >= trade.stop_price_current
    
    def _check_any_target_hit(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> bool:
        """Check if any remaining target was hit."""
        for target_price, _ in trade.targets:
            if trade.direction == 'long':
                if bar_high >= target_price:
                    return True
            else:
                if bar_low <= target_price:
                    return True
        return False
    
    def _check_partial_fills(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
        bar_timestamp: datetime,
    ) -> List[TradeEvent]:
        """Check for partial target fills."""
        events = []
        
        for i, (target_price, size_fraction) in enumerate(trade.targets):
            # Check if already filled
            already_filled = any(pf.target_number == i + 1 for pf in trade.partials_filled)
            if already_filled:
                continue
            
            # Check if target hit
            hit = False
            if trade.direction == 'long':
                hit = bar_high >= target_price
            else:
                hit = bar_low <= target_price
            
            if hit:
                # Record partial fill
                r_at_fill = trade.compute_current_r(target_price)
                
                partial = PartialFill(
                    timestamp=bar_timestamp,
                    price=target_price,
                    size_fraction=size_fraction,
                    target_number=i + 1,
                    r_multiple=r_at_fill,
                )
                
                trade.partials_filled.append(partial)
                trade.remaining_size -= size_fraction
                
                logger.info(
                    f"Partial fill T{i+1}: {size_fraction:.0%} @ {target_price:.2f} "
                    f"({r_at_fill:.2f}R), remaining={trade.remaining_size:.0%}"
                )
                
                events.append(TradeEvent.PARTIAL_FILL)
        
        return events
    
    def _close_on_stop(
        self,
        trade: ActiveTrade,
        timestamp: datetime,
    ) -> ActiveTrade:
        """Close trade on stop hit."""
        trade.exit_timestamp = timestamp
        trade.exit_price = trade.stop_price_current
        trade.exit_reason = 'stop'
        trade.realized_r = self._compute_realized_r(trade)
        
        logger.info(
            f"Stop hit: {trade.trade_id} closed @ {trade.exit_price:.2f}, "
            f"R={trade.realized_r:.2f}"
        )
        
        return trade
    
    def _compute_realized_r(self, trade: ActiveTrade) -> float:
        """Compute realized R-multiple for closed trade."""
        if not trade.is_closed:
            return 0.0
        
        total_r = 0.0
        
        # Add partial fills
        for partial in trade.partials_filled:
            total_r += partial.r_multiple * partial.size_fraction
        
        # Add final exit if remaining size
        if trade.remaining_size > 0.001:
            final_r = trade.compute_current_r(trade.exit_price)
            total_r += final_r * trade.remaining_size
        
        return total_r





