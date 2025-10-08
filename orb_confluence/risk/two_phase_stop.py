"""Two-phase stop system for adaptive risk management.

Phase 1 (Statistical): Tight stop based on winner MAE distribution
Phase 2 (Expansion): Wider stop at structural levels after reaching threshold
Phase 3 (Runner): Optional trail for extended moves

Logic:
1. Trade starts in Phase 1 with statistical stop
2. Once MFE >= phase2_trigger_r, transition to Phase 2
3. Phase 2 stop set to structural anchor (OR opposite, VWAP, pivot)
4. If MFE >= runner_trigger_r AND p_extension >= threshold, enable Phase 3
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from loguru import logger


class StopPhase(str, Enum):
    """Stop phase classification."""
    PHASE1_STATISTICAL = "PHASE1_STATISTICAL"  # Tight statistical stop
    PHASE2_EXPANSION = "PHASE2_EXPANSION"  # Wider structural stop
    PHASE3_RUNNER = "PHASE3_RUNNER"  # Trail for extended move


@dataclass
class StopUpdate:
    """Stop update event record."""
    
    timestamp: datetime
    old_stop: float
    new_stop: float
    old_phase: StopPhase
    new_phase: StopPhase
    reason: str
    current_mfe_r: float
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"StopUpdate({self.old_phase} → {self.new_phase}, "
            f"stop {self.old_stop:.2f} → {self.new_stop:.2f}, "
            f"MFE={self.current_mfe_r:.2f}R, reason='{self.reason}')"
        )


class TwoPhaseStopManager:
    """Manages two-phase stop evolution for a single trade.
    
    Phase transitions:
    - Phase 1 → Phase 2: When MFE >= phase2_trigger_r
    - Phase 2 → Phase 3: When MFE >= runner_trigger_r AND p_extension OK
    
    Stop updates:
    - Phase 1: Fixed at statistical_stop_distance
    - Phase 2: Max(current_stop, structural_anchor - buffer)
    - Phase 3: Trailing stop (managed by trailing module)
    
    Example:
        >>> manager = TwoPhaseStopManager(
        ...     direction="long",
        ...     entry_price=5000.0,
        ...     initial_risk=5.0,
        ...     phase1_stop_distance=4.0,
        ...     phase2_trigger_r=0.6,
        ...     structural_anchor=4995.0
        ... )
        >>> 
        >>> # On each bar
        >>> stop_update = manager.update(
        ...     current_price=5008.0,
        ...     current_mfe_r=1.6,
        ...     timestamp=datetime.now()
        ... )
        >>> 
        >>> if stop_update:
        ...     print(f"Stop updated: {stop_update}")
    """
    
    def __init__(
        self,
        direction: str,
        entry_price: float,
        initial_risk: float,
        phase1_stop_distance: float,  # In price units (e.g., from 80th %ile winner MAE)
        phase2_trigger_r: float = 0.6,
        runner_trigger_r: float = 1.5,
        structural_anchor: Optional[float] = None,
        structural_buffer: float = 0.0,
        p_extension: Optional[float] = None,
        p_extension_threshold: float = 0.42,
        stop_multiplier: float = 1.3,  # ✨ OPTIMIZATION: Widen stops to reduce noise stop-outs
        breakeven_trigger_r: float = 0.3,  # ✨ OPTIMIZATION: Move to breakeven at +0.3R MFE
    ) -> None:
        """Initialize two-phase stop manager.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            initial_risk: Initial risk (|entry - initial_stop|)
            phase1_stop_distance: Phase 1 stop distance from entry
            phase2_trigger_r: MFE threshold to trigger Phase 2
            runner_trigger_r: MFE threshold to enable Phase 3
            structural_anchor: Structural price level for Phase 2 stop
            structural_buffer: Buffer from structural anchor
            p_extension: Probability of extension (for runner gate)
            p_extension_threshold: Min p_extension to enable runner
            stop_multiplier: Multiplier for initial stop distance (1.3 = 30% wider)
            breakeven_trigger_r: MFE threshold to move stop to breakeven
        """
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.initial_risk = initial_risk
        self.phase1_distance = phase1_stop_distance * stop_multiplier  # ✨ Apply multiplier
        self.phase2_trigger = phase2_trigger_r
        self.runner_trigger = runner_trigger_r
        self.structural_anchor = structural_anchor
        self.structural_buffer = structural_buffer
        self.p_extension = p_extension
        self.p_threshold = p_extension_threshold
        self.stop_multiplier = stop_multiplier
        self.breakeven_trigger = breakeven_trigger_r
        
        # Current state
        self.current_phase = StopPhase.PHASE1_STATISTICAL
        self.current_stop = self._compute_phase1_stop()
        self.highest_mfe_r = 0.0
        self.breakeven_applied = False  # ✨ Track if breakeven already applied
        
        # History
        self.stop_updates: list[StopUpdate] = []
    
    def _compute_phase1_stop(self) -> float:
        """Compute Phase 1 stop price.
        
        Returns:
            Stop price
        """
        if self.direction == "long":
            return self.entry_price - self.phase1_distance
        else:  # short
            return self.entry_price + self.phase1_distance
    
    def _compute_phase2_stop(self) -> float:
        """Compute Phase 2 stop price.
        
        Uses structural anchor if available, otherwise fallback.
        
        Returns:
            Stop price
        """
        if self.structural_anchor is None:
            # Fallback: OR opposite or entry - 0.5R
            if self.direction == "long":
                return self.entry_price - self.initial_risk * 0.5
            else:
                return self.entry_price + self.initial_risk * 0.5
        
        # Use structural anchor with buffer
        if self.direction == "long":
            return self.structural_anchor - self.structural_buffer
        else:  # short
            return self.structural_anchor + self.structural_buffer
    
    def update(
        self,
        current_price: float,
        current_mfe_r: float,
        timestamp: datetime,
        new_structural_anchor: Optional[float] = None,
    ) -> Optional[StopUpdate]:
        """Update stop based on current market state.
        
        Args:
            current_price: Current market price
            current_mfe_r: Current MFE in R-multiples
            timestamp: Current timestamp
            new_structural_anchor: Optional updated structural anchor
            
        Returns:
            StopUpdate if stop changed, None otherwise
        """
        # Update highest MFE
        if current_mfe_r > self.highest_mfe_r:
            self.highest_mfe_r = current_mfe_r
        
        # Update structural anchor if provided
        if new_structural_anchor is not None:
            self.structural_anchor = new_structural_anchor
        
        old_stop = self.current_stop
        old_phase = self.current_phase
        new_stop = old_stop
        new_phase = old_phase
        reason = ""
        
        # Phase transition logic
        if self.current_phase == StopPhase.PHASE1_STATISTICAL:
            # ✨ OPTIMIZATION: Check for breakeven move first (at +0.3R MFE)
            if not self.breakeven_applied and current_mfe_r >= self.breakeven_trigger:
                # Move stop to breakeven (entry price)
                new_stop = self.entry_price
                # Ensure we're moving stop in favorable direction only
                if self.direction == "long":
                    new_stop = max(new_stop, old_stop)
                else:
                    new_stop = min(new_stop, old_stop)
                
                if new_stop != old_stop:  # Only record if actually moved
                    self.breakeven_applied = True
                    reason = f"Breakeven move at {current_mfe_r:.2f}R MFE"
                    logger.info(f"Trade moved to breakeven: stop {old_stop:.2f} → {new_stop:.2f}")
            
            # Check for Phase 2 transition
            elif current_mfe_r >= self.phase2_trigger:
                new_phase = StopPhase.PHASE2_EXPANSION
                new_stop = self._compute_phase2_stop()
                # Only move stop up (long) or down (short), never against direction
                if self.direction == "long":
                    new_stop = max(new_stop, old_stop)
                else:
                    new_stop = min(new_stop, old_stop)
                reason = f"Phase 2 transition at {current_mfe_r:.2f}R MFE"
                logger.info(f"Trade transition: Phase 1 → Phase 2, stop {old_stop:.2f} → {new_stop:.2f}")
        
        elif self.current_phase == StopPhase.PHASE2_EXPANSION:
            # Check for Phase 3 transition (runner)
            if current_mfe_r >= self.runner_trigger:
                # Check p_extension gate
                if self.p_extension is not None and self.p_extension >= self.p_threshold:
                    new_phase = StopPhase.PHASE3_RUNNER
                    reason = f"Runner enabled at {current_mfe_r:.2f}R (p={self.p_extension:.2f})"
                    logger.info(f"Trade transition: Phase 2 → Phase 3 (runner)")
                else:
                    # Don't transition, but could tighten stop
                    pass
            
            # In Phase 2, can update structural stop if better level found
            potential_stop = self._compute_phase2_stop()
            if self.direction == "long" and potential_stop > old_stop:
                new_stop = potential_stop
                reason = "Updated structural anchor"
            elif self.direction == "short" and potential_stop < old_stop:
                new_stop = potential_stop
                reason = "Updated structural anchor"
        
        elif self.current_phase == StopPhase.PHASE3_RUNNER:
            # Trailing logic handled by trailing module
            # This manager just tracks phase
            pass
        
        # Create update record if something changed
        if new_stop != old_stop or new_phase != old_phase:
            update = StopUpdate(
                timestamp=timestamp,
                old_stop=old_stop,
                new_stop=new_stop,
                old_phase=old_phase,
                new_phase=new_phase,
                reason=reason,
                current_mfe_r=current_mfe_r,
            )
            self.stop_updates.append(update)
            self.current_stop = new_stop
            self.current_phase = new_phase
            return update
        
        return None
    
    def check_stop_hit(self, current_price: float) -> bool:
        """Check if stop has been hit.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if stop hit, False otherwise
        """
        if self.direction == "long":
            return current_price <= self.current_stop
        else:  # short
            return current_price >= self.current_stop
    
    def get_stop_distance_r(self) -> float:
        """Get current stop distance in R-multiples.
        
        Returns:
            Stop distance in R
        """
        if self.initial_risk <= 0:
            return 0.0
        
        distance = abs(self.entry_price - self.current_stop)
        return distance / self.initial_risk
    
    @property
    def is_in_runner_phase(self) -> bool:
        """Check if trade is in runner phase."""
        return self.current_phase == StopPhase.PHASE3_RUNNER
    
    @property
    def phase(self) -> StopPhase:
        """Get current phase."""
        return self.current_phase
    
    @property
    def stop_price(self) -> float:
        """Get current stop price."""
        return self.current_stop


def compute_phase1_stop_from_mae_distribution(
    winner_mae_values: list[float],
    percentile: float = 80.0,
) -> float:
    """Compute Phase 1 stop distance from winner MAE distribution.
    
    Args:
        winner_mae_values: List of MAE values (R-multiples) from winning trades
        percentile: Percentile to use (e.g., 80th = accommodates 80% of winners)
        
    Returns:
        Stop distance in R-multiples
    """
    import numpy as np
    
    if not winner_mae_values:
        return 1.0  # Default fallback
    
    # MAE is negative, so take absolute value
    abs_mae = [abs(mae) for mae in winner_mae_values]
    
    # Get percentile
    stop_r = np.percentile(abs_mae, percentile)
    
    return float(stop_r)

