"""Trade manager for lifecycle management of active positions.

Handles bar-by-bar trade updates including partial fills, stop adjustments,
and exit detection.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

import pandas as pd
from loguru import logger

from .trade_state import ActiveTrade, PartialFill


class TradeEvent(str, Enum):
    """Trade event types."""
    
    PARTIAL_FILL = "partial_fill"
    BREAKEVEN_MOVE = "breakeven_move"
    STOP_HIT = "stop_hit"
    TARGET_HIT = "target_hit"


@dataclass
class TradeUpdate:
    """Result of trade update operation.
    
    Attributes:
        trade: Updated trade object
        events: List of events that occurred
        closed: Whether trade was closed
    """
    
    trade: ActiveTrade
    events: List[TradeEvent]
    closed: bool


class TradeManager:
    """Manages active trade lifecycle.
    
    Handles bar-by-bar updates including:
    - Partial target fills
    - Breakeven stop adjustment
    - Stop and final target exits
    - Conservative fill assumption (stop before target)
    
    Example:
        >>> manager = TradeManager(conservative_fills=True)
        >>> trade = ActiveTrade(...)
        >>> 
        >>> for bar in bars:
        ...     update = manager.update(trade, bar)
        ...     if TradeEvent.PARTIAL_FILL in update.events:
        ...         print(f"Partial fill: {update.trade.partials_filled[-1]}")
        ...     if update.closed:
        ...         print(f"Trade closed: {update.trade.exit_reason}")
        ...         break
    """
    
    def __init__(
        self,
        conservative_fills: bool = True,
        move_be_at_r: float = 1.0,
        be_buffer: float = 0.0,
    ):
        """Initialize trade manager.
        
        Args:
            conservative_fills: If both stop and target hit in bar, assume stop first.
            move_be_at_r: Move stop to breakeven after this R achieved.
            be_buffer: Buffer when moving to breakeven.
        """
        self.conservative_fills = conservative_fills
        self.move_be_at_r = move_be_at_r
        self.be_buffer = be_buffer
    
    def update(
        self,
        trade: ActiveTrade,
        bar: pd.Series,
    ) -> TradeUpdate:
        """Update trade with new bar.
        
        Args:
            trade: Active trade to update.
            bar: Current bar with timestamp_utc, open, high, low, close.
            
        Returns:
            TradeUpdate with modified trade, events, and closed flag.
            
        Notes:
            - Checks targets in order (T1, T2, runner)
            - Applies breakeven adjustment if threshold reached
            - Conservative fills: stop precedence if both hit
            
        Examples:
            >>> trade = ActiveTrade(
            ...     trade_id='TEST_1',
            ...     direction='long',
            ...     entry_price=100.0,
            ...     stop_price_current=99.0,
            ...     targets=[(101.0, 0.5), (102.0, 0.5)]
            ... )
            >>> bar = pd.Series({'high': 101.5, 'low': 100.5, ...})
            >>> update = manager.update(trade, bar)
            >>> assert TradeEvent.PARTIAL_FILL in update.events
        """
        events = []
        
        if trade.is_closed:
            logger.warning(f"Attempted to update closed trade: {trade.trade_id}")
            return TradeUpdate(trade=trade, events=[], closed=True)
        
        # Update R extremes
        bar_high = bar['high']
        bar_low = bar['low']
        bar_timestamp = bar['timestamp_utc']
        
        # Check high and low for R tracking
        trade.update_r_extremes(bar_high)
        trade.update_r_extremes(bar_low)
        
        # Conservative fills: check if both stop and target hit
        stop_hit = self._check_stop_hit(trade, bar_high, bar_low)
        target_hit = self._check_any_target_hit(trade, bar_high, bar_low)
        
        if self.conservative_fills and stop_hit and target_hit:
            # Both hit: assume stop hit first (conservative)
            logger.debug(f"Conservative fill: stop and target both hit, assuming stop first")
            trade = self._close_on_stop(trade, bar_timestamp)
            events.append(TradeEvent.STOP_HIT)
            return TradeUpdate(trade=trade, events=events, closed=True)
        
        # Check for stop hit
        if stop_hit:
            trade = self._close_on_stop(trade, bar_timestamp)
            events.append(TradeEvent.STOP_HIT)
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
            return TradeUpdate(trade=trade, events=events, closed=True)
        
        # Check for breakeven adjustment
        if not trade.moved_to_breakeven:
            be_moved = self._check_breakeven_move(trade, bar_high, bar_low)
            if be_moved:
                events.append(TradeEvent.BREAKEVEN_MOVE)
        
        return TradeUpdate(trade=trade, events=events, closed=False)
    
    def _check_stop_hit(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> bool:
        """Check if stop was hit in bar.
        
        Args:
            trade: Active trade.
            bar_high: Bar high price.
            bar_low: Bar low price.
            
        Returns:
            True if stop hit.
        """
        if trade.direction == 'long':
            # Long stop: hit if bar.low <= stop
            return bar_low <= trade.stop_price_current
        else:  # short
            # Short stop: hit if bar.high >= stop
            return bar_high >= trade.stop_price_current
    
    def _check_any_target_hit(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> bool:
        """Check if any remaining target was hit.
        
        Args:
            trade: Active trade.
            bar_high: Bar high price.
            bar_low: Bar low price.
            
        Returns:
            True if any target hit.
        """
        for target_price, _ in trade.targets:
            if trade.direction == 'long':
                if bar_high >= target_price:
                    return True
            else:  # short
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
        """Check for partial target fills.
        
        Args:
            trade: Active trade (modified in place).
            bar_high: Bar high price.
            bar_low: Bar low price.
            bar_timestamp: Bar timestamp.
            
        Returns:
            List of PARTIAL_FILL events.
        """
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
            else:  # short
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
    
    def _check_breakeven_move(
        self,
        trade: ActiveTrade,
        bar_high: float,
        bar_low: float,
    ) -> bool:
        """Check if breakeven adjustment should be applied.
        
        Args:
            trade: Active trade (modified in place).
            bar_high: Bar high price.
            bar_low: Bar low price.
            
        Returns:
            True if breakeven move occurred.
        """
        # Use most favorable price in bar
        if trade.direction == 'long':
            favorable_price = bar_high
        else:
            favorable_price = bar_low
        
        current_r = trade.compute_current_r(favorable_price)
        
        if current_r >= self.move_be_at_r:
            # Move to breakeven
            if trade.direction == 'long':
                new_stop = trade.entry_price + self.be_buffer
            else:
                new_stop = trade.entry_price - self.be_buffer
            
            old_stop = trade.stop_price_current
            trade.stop_price_current = new_stop
            trade.moved_to_breakeven = True
            trade.breakeven_price = new_stop
            
            logger.info(
                f"Stop moved to breakeven: {old_stop:.2f} → {new_stop:.2f} "
                f"(R={current_r:.2f} >= {self.move_be_at_r:.2f})"
            )
            
            return True
        
        return False
    
    def _close_on_stop(
        self,
        trade: ActiveTrade,
        timestamp: datetime,
    ) -> ActiveTrade:
        """Close trade on stop hit.
        
        Args:
            trade: Active trade (modified in place).
            timestamp: Exit timestamp.
            
        Returns:
            Modified trade.
        """
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
        """Compute realized R-multiple for closed trade.
        
        Takes into account partial fills with different R-multiples.
        
        Args:
            trade: Closed trade.
            
        Returns:
            Weighted average R-multiple.
        """
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
