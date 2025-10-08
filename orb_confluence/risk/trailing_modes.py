"""Trailing stop modes for adaptive exit management.

Implements multiple trailing strategies:
- TRAIL_VOL: ATR-based envelope trailing
- TRAIL_PIVOT: Structural pivot-based trailing
- HYBRID_VOL_PIVOT: Pivot priority with ATR fallback
- SINGLE_TARGET: Fixed target (for reversion trades)
- PARTIAL_THEN_TRAIL: Partial exit then switch to trail
- TIME_DECAY_FORCE: Force exit on time/slope decay
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List

import numpy as np
from loguru import logger

from ..playbooks.base import ExitMode


@dataclass
class TrailUpdate:
    """Trail stop update event."""
    
    timestamp: datetime
    old_stop: float
    new_stop: float
    reason: str
    current_mfe_r: float
    trail_mode: ExitMode
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"TrailUpdate({self.trail_mode.value}, "
            f"{self.old_stop:.2f} → {self.new_stop:.2f}, "
            f"MFE={self.current_mfe_r:.2f}R)"
        )


@dataclass
class PivotLevel:
    """Structural pivot level."""
    
    timestamp: datetime
    price: float
    pivot_type: str  # "swing_high" or "swing_low"
    confirmed: bool = False
    
    def __repr__(self) -> str:
        """String representation."""
        return f"Pivot({self.pivot_type} @ {self.price:.2f})"


class TrailingStopStrategy(ABC):
    """Abstract base for trailing stop strategies."""
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_stop: float,
    ) -> None:
        """Initialize trailing strategy.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop price
        """
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.current_stop = initial_stop
        self.highest_favorable = entry_price
        self.trail_updates: List[TrailUpdate] = []
    
    @abstractmethod
    def update(
        self,
        current_price: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
        **kwargs
    ) -> Optional[TrailUpdate]:
        """Update trailing stop.
        
        Args:
            current_price: Current price
            bar_high: Bar high
            bar_low: Bar low
            timestamp: Current timestamp
            **kwargs: Strategy-specific parameters
            
        Returns:
            TrailUpdate if stop moved, None otherwise
        """
        pass
    
    def _create_update(
        self,
        new_stop: float,
        reason: str,
        current_mfe_r: float,
        timestamp: datetime,
        mode: ExitMode,
    ) -> Optional[TrailUpdate]:
        """Create trail update if stop improved.
        
        Args:
            new_stop: New stop price
            reason: Update reason
            current_mfe_r: Current MFE
            timestamp: Update timestamp
            mode: Exit mode
            
        Returns:
            TrailUpdate if stop improved, None otherwise
        """
        old_stop = self.current_stop
        
        # Check if stop improved (only move in favorable direction)
        improved = False
        if self.direction == "long":
            improved = new_stop > old_stop
        else:  # short
            improved = new_stop < old_stop
        
        if improved:
            update = TrailUpdate(
                timestamp=timestamp,
                old_stop=old_stop,
                new_stop=new_stop,
                reason=reason,
                current_mfe_r=current_mfe_r,
                trail_mode=mode,
            )
            self.current_stop = new_stop
            self.trail_updates.append(update)
            return update
        
        return None
    
    def check_stop_hit(self, current_price: float) -> bool:
        """Check if stop hit.
        
        Args:
            current_price: Current price
            
        Returns:
            True if stop hit
        """
        if self.direction == "long":
            return current_price <= self.current_stop
        else:
            return current_price >= self.current_stop


class VolatilityTrailingStop(TrailingStopStrategy):
    """ATR-based envelope trailing.
    
    Stop trails at fixed ATR multiple below/above highest favorable price.
    
    Example:
        >>> trail = VolatilityTrailingStop(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_stop=4995.0,
        ...     atr_multiple=2.0
        ... )
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_stop: float,
        atr_multiple: float = 2.0,
        initial_risk: float = 5.0,
    ) -> None:
        """Initialize volatility trailing.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop
            atr_multiple: ATR multiple for trail distance
            initial_risk: Initial risk for R calculations
        """
        super().__init__(direction, entry_price, initial_stop)
        self.atr_multiple = atr_multiple
        self.initial_risk = initial_risk
    
    def update(
        self,
        current_price: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
        atr: float = None,
        **kwargs
    ) -> Optional[TrailUpdate]:
        """Update volatility trail.
        
        Args:
            current_price: Current price
            bar_high: Bar high
            bar_low: Bar low
            timestamp: Timestamp
            atr: Current ATR value
            **kwargs: Ignored
            
        Returns:
            TrailUpdate if stop moved
        """
        if atr is None:
            logger.warning("ATR not provided for volatility trailing")
            return None
        
        # Update highest favorable
        if self.direction == "long":
            if bar_high > self.highest_favorable:
                self.highest_favorable = bar_high
        else:  # short
            if bar_low < self.highest_favorable:
                self.highest_favorable = bar_low
        
        # Compute trail distance
        trail_distance = self.atr_multiple * atr
        
        # New stop at trail distance from highest favorable
        if self.direction == "long":
            new_stop = self.highest_favorable - trail_distance
        else:  # short
            new_stop = self.highest_favorable + trail_distance
        
        # Compute MFE
        if self.initial_risk > 0:
            if self.direction == "long":
                current_mfe_r = (self.highest_favorable - self.entry_price) / self.initial_risk
            else:
                current_mfe_r = (self.entry_price - self.highest_favorable) / self.initial_risk
        else:
            current_mfe_r = 0.0
        
        return self._create_update(
            new_stop=new_stop,
            reason=f"ATR trail: {self.atr_multiple}x{atr:.2f} from {self.highest_favorable:.2f}",
            current_mfe_r=current_mfe_r,
            timestamp=timestamp,
            mode=ExitMode.TRAIL_VOL,
        )


class PivotTrailingStop(TrailingStopStrategy):
    """Structural pivot-based trailing.
    
    Stop trails under/over confirmed swing pivots.
    
    Example:
        >>> trail = PivotTrailingStop(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_stop=4995.0,
        ...     pivot_lookback=3
        ... )
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_stop: float,
        pivot_lookback: int = 3,
        buffer_atr_mult: float = 0.1,
        initial_risk: float = 5.0,
    ) -> None:
        """Initialize pivot trailing.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop
            pivot_lookback: Bars for pivot confirmation
            buffer_atr_mult: Buffer below pivot (ATR mult)
            initial_risk: Initial risk for R calculations
        """
        super().__init__(direction, entry_price, initial_stop)
        self.pivot_lookback = pivot_lookback
        self.buffer_mult = buffer_atr_mult
        self.initial_risk = initial_risk
        
        # Track recent bars for pivot detection
        self.recent_bars: List[dict] = []
        self.confirmed_pivots: List[PivotLevel] = []
    
    def update(
        self,
        current_price: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
        atr: float = None,
        **kwargs
    ) -> Optional[TrailUpdate]:
        """Update pivot trail.
        
        Args:
            current_price: Current price
            bar_high: Bar high
            bar_low: Bar low
            timestamp: Timestamp
            atr: Current ATR (for buffer)
            **kwargs: Ignored
            
        Returns:
            TrailUpdate if stop moved
        """
        # Store bar
        self.recent_bars.append({
            "timestamp": timestamp,
            "high": bar_high,
            "low": bar_low,
            "close": current_price,
        })
        
        # Keep only necessary bars
        if len(self.recent_bars) > self.pivot_lookback * 2 + 10:
            self.recent_bars.pop(0)
        
        # Update highest favorable
        if self.direction == "long":
            if bar_high > self.highest_favorable:
                self.highest_favorable = bar_high
        else:
            if bar_low < self.highest_favorable:
                self.highest_favorable = bar_low
        
        # Detect new pivots
        self._detect_pivots()
        
        # Find best pivot for stop
        best_pivot = self._find_best_pivot()
        
        if best_pivot is None:
            return None
        
        # Compute stop with buffer
        buffer = self.buffer_mult * atr if atr is not None else 0.0
        
        if self.direction == "long":
            new_stop = best_pivot.price - buffer
        else:  # short
            new_stop = best_pivot.price + buffer
        
        # Compute MFE
        if self.initial_risk > 0:
            if self.direction == "long":
                current_mfe_r = (self.highest_favorable - self.entry_price) / self.initial_risk
            else:
                current_mfe_r = (self.entry_price - self.highest_favorable) / self.initial_risk
        else:
            current_mfe_r = 0.0
        
        return self._create_update(
            new_stop=new_stop,
            reason=f"Pivot trail: {best_pivot.pivot_type} @ {best_pivot.price:.2f}",
            current_mfe_r=current_mfe_r,
            timestamp=timestamp,
            mode=ExitMode.TRAIL_PIVOT,
        )
    
    def _detect_pivots(self) -> None:
        """Detect swing pivots in recent bars."""
        if len(self.recent_bars) < self.pivot_lookback * 2 + 1:
            return
        
        # Check middle bar for pivot
        mid_idx = len(self.recent_bars) - self.pivot_lookback - 1
        if mid_idx < self.pivot_lookback:
            return
        
        mid_bar = self.recent_bars[mid_idx]
        
        # Swing low: mid low < all lookback bars on each side
        if self.direction == "long":
            is_swing_low = True
            for i in range(mid_idx - self.pivot_lookback, mid_idx + self.pivot_lookback + 1):
                if i == mid_idx:
                    continue
                if i < 0 or i >= len(self.recent_bars):
                    is_swing_low = False
                    break
                if self.recent_bars[i]["low"] <= mid_bar["low"]:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                pivot = PivotLevel(
                    timestamp=mid_bar["timestamp"],
                    price=mid_bar["low"],
                    pivot_type="swing_low",
                    confirmed=True,
                )
                # Add if not duplicate
                if not any(p.price == pivot.price for p in self.confirmed_pivots):
                    self.confirmed_pivots.append(pivot)
        
        # Swing high: mid high > all lookback bars on each side
        else:  # short
            is_swing_high = True
            for i in range(mid_idx - self.pivot_lookback, mid_idx + self.pivot_lookback + 1):
                if i == mid_idx:
                    continue
                if i < 0 or i >= len(self.recent_bars):
                    is_swing_high = False
                    break
                if self.recent_bars[i]["high"] >= mid_bar["high"]:
                    is_swing_high = False
                    break
            
            if is_swing_high:
                pivot = PivotLevel(
                    timestamp=mid_bar["timestamp"],
                    price=mid_bar["high"],
                    pivot_type="swing_high",
                    confirmed=True,
                )
                if not any(p.price == pivot.price for p in self.confirmed_pivots):
                    self.confirmed_pivots.append(pivot)
        
        # Keep only recent pivots
        if len(self.confirmed_pivots) > 5:
            self.confirmed_pivots.pop(0)
    
    def _find_best_pivot(self) -> Optional[PivotLevel]:
        """Find best pivot for stop placement.
        
        Returns:
            Best PivotLevel or None
        """
        if not self.confirmed_pivots:
            return None
        
        # For long: find highest swing low below current price
        # For short: find lowest swing high above current price
        
        if self.direction == "long":
            valid_pivots = [
                p for p in self.confirmed_pivots
                if p.pivot_type == "swing_low" and p.price < self.highest_favorable
            ]
            if valid_pivots:
                return max(valid_pivots, key=lambda p: p.price)
        else:  # short
            valid_pivots = [
                p for p in self.confirmed_pivots
                if p.pivot_type == "swing_high" and p.price > self.highest_favorable
            ]
            if valid_pivots:
                return min(valid_pivots, key=lambda p: p.price)
        
        return None


class HybridTrailingStop(TrailingStopStrategy):
    """Hybrid pivot + volatility trailing.
    
    Uses pivot stops when available, falls back to ATR when no pivots.
    
    Example:
        >>> trail = HybridTrailingStop(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_stop=4995.0,
        ...     atr_multiple=1.8
        ... )
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_stop: float,
        atr_multiple: float = 1.8,
        pivot_lookback: int = 3,
        initial_risk: float = 5.0,
    ) -> None:
        """Initialize hybrid trailing.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop
            atr_multiple: ATR multiple for fallback
            pivot_lookback: Pivot confirmation bars
            initial_risk: Initial risk
        """
        super().__init__(direction, entry_price, initial_stop)
        
        # Create both strategies
        self.pivot_trail = PivotTrailingStop(
            direction=direction,
            entry_price=entry_price,
            initial_stop=initial_stop,
            pivot_lookback=pivot_lookback,
            initial_risk=initial_risk,
        )
        
        self.vol_trail = VolatilityTrailingStop(
            direction=direction,
            entry_price=entry_price,
            initial_stop=initial_stop,
            atr_multiple=atr_multiple,
            initial_risk=initial_risk,
        )
    
    def update(
        self,
        current_price: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
        atr: float = None,
        **kwargs
    ) -> Optional[TrailUpdate]:
        """Update hybrid trail.
        
        Prefers pivot, falls back to vol.
        
        Args:
            current_price: Current price
            bar_high: Bar high
            bar_low: Bar low
            timestamp: Timestamp
            atr: ATR value
            **kwargs: Ignored
            
        Returns:
            TrailUpdate if stop moved
        """
        # Try pivot first
        pivot_update = self.pivot_trail.update(
            current_price=current_price,
            bar_high=bar_high,
            bar_low=bar_low,
            timestamp=timestamp,
            atr=atr,
        )
        
        # Update vol trail too
        vol_update = self.vol_trail.update(
            current_price=current_price,
            bar_high=bar_high,
            bar_low=bar_low,
            timestamp=timestamp,
            atr=atr,
        )
        
        # Use best stop (most favorable)
        pivot_stop = self.pivot_trail.current_stop
        vol_stop = self.vol_trail.current_stop
        
        if self.direction == "long":
            best_stop = max(pivot_stop, vol_stop)
            reason_suffix = "pivot" if best_stop == pivot_stop else "ATR fallback"
        else:  # short
            best_stop = min(pivot_stop, vol_stop)
            reason_suffix = "pivot" if best_stop == pivot_stop else "ATR fallback"
        
        # Update highest favorable
        self.highest_favorable = max(self.pivot_trail.highest_favorable, self.vol_trail.highest_favorable)
        
        # Compute MFE
        initial_risk = self.pivot_trail.initial_risk
        if initial_risk > 0:
            if self.direction == "long":
                current_mfe_r = (self.highest_favorable - self.entry_price) / initial_risk
            else:
                current_mfe_r = (self.entry_price - self.highest_favorable) / initial_risk
        else:
            current_mfe_r = 0.0
        
        return self._create_update(
            new_stop=best_stop,
            reason=f"Hybrid trail: {reason_suffix}",
            current_mfe_r=current_mfe_r,
            timestamp=timestamp,
            mode=ExitMode.HYBRID_VOL_PIVOT,
        )


class TrailingStopManager:
    """Manager for all trailing stop strategies.
    
    Routes to appropriate strategy based on exit mode.
    
    Example:
        >>> manager = TrailingStopManager(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_stop=4995.0,
        ...     exit_mode=ExitMode.TRAIL_VOL,
        ...     atr_multiple=2.0
        ... )
        >>> 
        >>> update = manager.update(
        ...     current_price=5008.0,
        ...     bar_high=5010.0,
        ...     bar_low=5007.0,
        ...     timestamp=datetime.now(),
        ...     atr=2.5
        ... )
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_stop: float,
        exit_mode: ExitMode,
        initial_risk: float,
        **mode_params
    ) -> None:
        """Initialize trailing manager.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_stop: Initial stop
            exit_mode: Exit mode to use
            initial_risk: Initial risk
            **mode_params: Mode-specific parameters
        """
        self.exit_mode = exit_mode
        
        # Create appropriate strategy
        if exit_mode == ExitMode.TRAIL_VOL:
            self.strategy = VolatilityTrailingStop(
                direction=direction,
                entry_price=entry_price,
                initial_stop=initial_stop,
                atr_multiple=mode_params.get("trail_factor", 2.0),
                initial_risk=initial_risk,
            )
        
        elif exit_mode == ExitMode.TRAIL_PIVOT:
            self.strategy = PivotTrailingStop(
                direction=direction,
                entry_price=entry_price,
                initial_stop=initial_stop,
                pivot_lookback=mode_params.get("pivot_lookback", 3),
                initial_risk=initial_risk,
            )
        
        elif exit_mode == ExitMode.HYBRID_VOL_PIVOT:
            self.strategy = HybridTrailingStop(
                direction=direction,
                entry_price=entry_price,
                initial_stop=initial_stop,
                atr_multiple=mode_params.get("trail_factor", 1.8),
                initial_risk=initial_risk,
            )
        
        else:
            # Default to volatility
            self.strategy = VolatilityTrailingStop(
                direction=direction,
                entry_price=entry_price,
                initial_stop=initial_stop,
                atr_multiple=2.0,
                initial_risk=initial_risk,
            )
    
    def update(self, **kwargs) -> Optional[TrailUpdate]:
        """Update trailing stop.
        
        Args:
            **kwargs: Passed to strategy update()
            
        Returns:
            TrailUpdate if stop moved
        """
        return self.strategy.update(**kwargs)
    
    def check_stop_hit(self, current_price: float) -> bool:
        """Check if stop hit.
        
        Args:
            current_price: Current price
            
        Returns:
            True if stop hit
        """
        return self.strategy.check_stop_hit(current_price)
    
    @property
    def current_stop(self) -> float:
        """Get current stop price."""
        return self.strategy.current_stop

