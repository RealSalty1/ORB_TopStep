"""PB1: Classic ORB Refined with state integration.

Enhancements over basic ORB:
- State-aware buffer calculation
- Dynamic buffer based on volatility + rotations
- Exit mode selection based on auction state
- Retest confirmation option
"""

from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from orb_confluence.states.auction_state import AuctionState
from .base import (
    Playbook,
    CandidateSignal,
    ExitMode,
    ExitModeDescriptor,
    SignalMetadata,
)


class ORBRefinedPlaybook(Playbook):
    """Refined ORB breakout playbook with state integration.
    
    Configuration:
    - buffer.base: Base buffer (ATR multiples)
    - buffer.vol_alpha: Volatility adjustment factor
    - buffer.rotation_penalty: Penalty per rotation
    - buffer.min: Minimum buffer
    - buffer.max: Maximum buffer
    - require_retest: Require pullback retest
    - phase2_trigger_r: MFE threshold for phase 2 stop
    
    Example:
        >>> playbook = ORBRefinedPlaybook(config={
        ...     "buffer": {
        ...         "base": 0.75,
        ...         "vol_alpha": 0.35,
        ...         "rotation_penalty": 0.10,
        ...         "min": 0.50,
        ...         "max": 2.00
        ...     }
        ... })
        >>> 
        >>> signals = playbook.generate_signals(context)
    """
    
    def __init__(self, name: str = "PB1_ORB_Refined", config: Optional[Dict] = None) -> None:
        """Initialize ORB Refined playbook.
        
        Args:
            name: Playbook name
            config: Configuration dictionary
        """
        super().__init__(name, config)
        
        # Buffer configuration
        buffer_config = self.config.get("buffer", {})
        self.base_buffer = buffer_config.get("base", 0.75)
        self.vol_alpha = buffer_config.get("vol_alpha", 0.35)
        self.rotation_penalty = buffer_config.get("rotation_penalty", 0.10)
        self.min_buffer = buffer_config.get("min", 0.50)
        self.max_buffer = buffer_config.get("max", 2.00)
        
        # Entry options
        self.require_retest = self.config.get("require_retest", False)
        
        # Risk parameters
        self.phase2_trigger_r = self.config.get("phase2_trigger_r", 0.6)
    
    def is_eligible(self, context: Dict) -> bool:
        """Check eligibility for ORB playbook.
        
        Eligible if:
        - Auction state is INITIATIVE or COMPRESSION (with acceptable width)
        - OR is finalized and valid
        - Not context_excluded
        
        Args:
            context: Market context dictionary
            
        Returns:
            True if eligible
        """
        if not self.enabled:
            return False
        
        # Check auction state
        auction_state = context.get("auction_state")
        if auction_state not in [
            AuctionState.INITIATIVE.value,
            AuctionState.COMPRESSION.value,
            AuctionState.BALANCED.value,  # Can work in balanced too
        ]:
            return False
        
        # Check OR validity
        or_finalized = context.get("or_primary_finalized", False)
        or_valid = context.get("or_primary_valid", True)
        if not or_finalized or not or_valid:
            return False
        
        # Check context exclusion
        if context.get("context_excluded", False):
            return False
        
        return True
    
    def generate_signals(self, context: Dict) -> List[CandidateSignal]:
        """Generate ORB breakout signals.
        
        Args:
            context: Market context with OR levels, price, features
            
        Returns:
            List of CandidateSignal (0-2, for long and/or short)
        """
        signals = []
        
        # Extract context
        current_price = context["current_price"]
        or_high = context["or_primary_high"]
        or_low = context["or_primary_low"]
        atr_14 = context["atr_14"]
        timestamp = context["timestamp"]
        
        # Compute dynamic buffer
        buffer_atr = self._compute_dynamic_buffer(context)
        buffer_price = buffer_atr * atr_14
        
        # Breakout triggers
        long_trigger = or_high + buffer_price
        short_trigger = or_low - buffer_price
        
        # Check for breakouts
        # Long breakout
        if current_price >= long_trigger:
            # Build signal
            signal = self._create_signal(
                direction="long",
                entry_price=current_price,
                trigger_price=long_trigger,
                buffer_used=buffer_atr,
                or_low=or_low,
                or_high=or_high,
                context=context,
                timestamp=timestamp,
            )
            signals.append(signal)
            logger.debug(f"ORB long signal: {signal}")
        
        # Short breakout
        if current_price <= short_trigger:
            signal = self._create_signal(
                direction="short",
                entry_price=current_price,
                trigger_price=short_trigger,
                buffer_used=buffer_atr,
                or_low=or_low,
                or_high=or_high,
                context=context,
                timestamp=timestamp,
            )
            signals.append(signal)
            logger.debug(f"ORB short signal: {signal}")
        
        return signals
    
    def _compute_dynamic_buffer(self, context: Dict) -> float:
        """Compute dynamic buffer in ATR multiples.
        
        Args:
            context: Market context
            
        Returns:
            Buffer in ATR multiples
        """
        # Base buffer
        buffer = self.base_buffer
        
        # Volatility adjustment
        # Get recent 1-minute return std as proxy for intraday vol
        recent_vol = context.get("recent_return_std", 0.0)
        vol_adjustment = self.vol_alpha * recent_vol
        buffer += vol_adjustment
        
        # Rotation penalty (higher rotations = choppier, need wider buffer)
        rotations = context.get("rotations", 0)
        rotation_adjustment = self.rotation_penalty * rotations
        buffer += rotation_adjustment
        
        # Clip to bounds
        buffer = np.clip(buffer, self.min_buffer, self.max_buffer)
        
        return buffer
    
    def _create_signal(
        self,
        direction: str,
        entry_price: float,
        trigger_price: float,
        buffer_used: float,
        or_low: float,
        or_high: float,
        context: Dict,
        timestamp,
    ) -> CandidateSignal:
        """Create candidate signal with all metadata.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            trigger_price: Breakout trigger price
            buffer_used: Buffer used (ATR multiples)
            or_low: OR low
            or_high: OR high
            context: Full context
            timestamp: Signal timestamp
            
        Returns:
            CandidateSignal
        """
        # Compute initial stop (opposite OR level)
        if direction == "long":
            initial_stop = or_low
            structural_anchor = or_low
        else:  # short
            initial_stop = or_high
            structural_anchor = or_high
        
        # Phase 1 stop distance (can be tighter than full OR opposite)
        # Use 80th percentile of winner MAE if available, else default
        phase1_distance = context.get("phase1_stop_distance", abs(entry_price - initial_stop) * 0.8)
        
        # Build metadata
        metadata = SignalMetadata(
            auction_state=context.get("auction_state", "UNKNOWN"),
            auction_state_confidence=context.get("auction_state_confidence", 0.0),
            or_width_norm=context.get("or_primary_width_norm", 0.0),
            breakout_delay_minutes=context.get("breakout_delay_minutes", 0.0),
            volume_quality_score=context.get("volume_quality_score", 0.5),
            normalized_vol=context.get("normalized_vol", 1.0),
            drive_energy=context.get("drive_energy", 0.0),
            rotations=context.get("rotations", 0),
            gap_type=context.get("gap_type", "NO_GAP"),
            p_extension=context.get("p_extension"),
        )
        
        # Select exit mode
        exit_mode = self.preferred_exit_mode(context)
        
        # Create signal
        signal = CandidateSignal(
            playbook_name=self.name,
            direction=direction,
            entry_price=entry_price,
            trigger_price=trigger_price,
            buffer_used=buffer_used,
            initial_stop=initial_stop,
            phase1_stop_distance=phase1_distance,
            structural_anchor=structural_anchor,
            exit_mode=exit_mode,
            metadata=metadata,
            timestamp=timestamp,
            priority=1.0,
        )
        
        return signal
    
    def preferred_exit_mode(self, context: Dict) -> ExitModeDescriptor:
        """Select exit mode based on auction state.
        
        Args:
            context: Market context
            
        Returns:
            ExitModeDescriptor
        """
        auction_state = context.get("auction_state")
        
        # INITIATIVE: Aggressive trail with small partial
        if auction_state == AuctionState.INITIATIVE.value:
            return ExitModeDescriptor(
                mode=ExitMode.PARTIAL_THEN_TRAIL,
                partial_size=0.2,  # 20% at first target
                partial_at_r=1.2,
                trail_factor=2.0,  # 2x ATR trail
            )
        
        # COMPRESSION: Tighter trail, larger partial
        elif auction_state == AuctionState.COMPRESSION.value:
            return ExitModeDescriptor(
                mode=ExitMode.PARTIAL_THEN_TRAIL,
                partial_size=0.4,  # 40% at first target
                partial_at_r=1.5,
                trail_factor=1.5,  # Tighter trail
            )
        
        # BALANCED: Hybrid approach
        elif auction_state == AuctionState.BALANCED.value:
            return ExitModeDescriptor(
                mode=ExitMode.HYBRID_VOL_PIVOT,
                trail_factor=1.8,
            )
        
        # Default
        else:
            return ExitModeDescriptor(
                mode=ExitMode.TRAIL_VOL,
                trail_factor=2.0,
            )

