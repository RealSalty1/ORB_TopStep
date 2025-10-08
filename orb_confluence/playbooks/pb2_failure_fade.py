"""PB2: OR Failure Fade - Counter-trend on failed breakouts.

Logic:
1. Detect wick-only break beyond OR (body closes back inside)
2. Volume fades on the rejection
3. Enter opposite direction at OR mid or rejection pivot
4. Target VWAP or opposite OR quartile
5. Time stop if no progress
"""

from typing import Dict, List, Optional

from loguru import logger

from .base import (
    Playbook,
    CandidateSignal,
    ExitMode,
    ExitModeDescriptor,
    SignalMetadata,
)


class FailureFadePlaybook(Playbook):
    """OR Failure Fade playbook.
    
    Configuration:
    - wick_ratio_min: Min wick/body ratio to qualify as wick-only (e.g., 0.55)
    - volume_fade_threshold: Volume ratio below avg to confirm fade
    - reenter_mid: Enter at OR mid vs rejection pivot
    - time_stop_minutes: Exit if no progress in X minutes
    
    Example:
        >>> playbook = FailureFadePlaybook(config={
        ...     "wick_ratio_min": 0.55,
        ...     "volume_fade_threshold": 0.8,
        ...     "reenter_mid": True,
        ...     "time_stop_minutes": 30
        ... })
    """
    
    def __init__(self, name: str = "PB2_Failure_Fade", config: Optional[Dict] = None) -> None:
        """Initialize Failure Fade playbook."""
        super().__init__(name, config)
        
        self.wick_ratio_min = self.config.get("wick_ratio_min", 0.55)
        self.volume_fade_threshold = self.config.get("volume_fade_threshold", 0.8)
        self.reenter_mid = self.config.get("reenter_mid", True)
        self.time_stop_minutes = self.config.get("time_stop_minutes", 30)
        
        # State tracking (per session)
        self.failed_breakout_high: Optional[float] = None
        self.failed_breakout_low: Optional[float] = None
        self.failure_detected = False
    
    def is_eligible(self, context: Dict) -> bool:
        """Check eligibility for failure fade.
        
        Eligible if:
        - OR finalized
        - Not already in failure mode (one failure per session)
        
        Args:
            context: Market context
            
        Returns:
            True if eligible
        """
        if not self.enabled:
            return False
        
        # Must have finalized OR
        if not context.get("or_primary_finalized", False):
            return False
        
        # Only take one failure trade per session
        if self.failure_detected:
            return False
        
        return True
    
    def generate_signals(self, context: Dict) -> List[CandidateSignal]:
        """Generate failure fade signals.
        
        Detects:
        1. Wick beyond OR with body back inside
        2. Volume fade
        3. Entry at mid or pivot
        
        Args:
            context: Market context
            
        Returns:
            List of CandidateSignal (0-1)
        """
        signals = []
        
        # Extract context
        current_bar = context.get("current_bar")
        if current_bar is None:
            return signals
        
        or_high = context["or_primary_high"]
        or_low = context["or_primary_low"]
        or_mid = (or_high + or_low) / 2.0
        
        bar_high = current_bar["high"]
        bar_low = current_bar["low"]
        bar_close = current_bar["close"]
        bar_open = current_bar["open"]
        
        # Detect wick-only failure
        # Upside failure: high > OR high, but close < OR high
        if bar_high > or_high and bar_close < or_high:
            body_size = abs(bar_close - bar_open)
            upper_wick = bar_high - max(bar_close, bar_open)
            
            if body_size > 0:
                wick_ratio = upper_wick / body_size
            else:
                wick_ratio = 1.0  # All wick
            
            # Check wick ratio
            if wick_ratio >= self.wick_ratio_min:
                # Check volume fade
                volume_ratio = context.get("volume_ratio", 1.0)
                if volume_ratio < self.volume_fade_threshold:
                    # Failure detected - short signal
                    self.failed_breakout_high = bar_high
                    self.failure_detected = True
                    
                    # Entry price
                    if self.reenter_mid:
                        entry_price = or_mid
                    else:
                        entry_price = or_high  # At rejection level
                    
                    # Only signal if price near entry
                    if abs(bar_close - entry_price) / entry_price < 0.002:  # Within 0.2%
                        signal = self._create_fade_signal(
                            direction="short",
                            entry_price=entry_price,
                            or_high=or_high,
                            or_low=or_low,
                            failure_extreme=bar_high,
                            context=context,
                        )
                        signals.append(signal)
                        logger.info(f"Failure fade SHORT detected: wick {wick_ratio:.2f}, vol {volume_ratio:.2f}")
        
        # Downside failure: low < OR low, but close > OR low
        elif bar_low < or_low and bar_close > or_low:
            body_size = abs(bar_close - bar_open)
            lower_wick = min(bar_close, bar_open) - bar_low
            
            if body_size > 0:
                wick_ratio = lower_wick / body_size
            else:
                wick_ratio = 1.0
            
            if wick_ratio >= self.wick_ratio_min:
                volume_ratio = context.get("volume_ratio", 1.0)
                if volume_ratio < self.volume_fade_threshold:
                    # Failure detected - long signal
                    self.failed_breakout_low = bar_low
                    self.failure_detected = True
                    
                    if self.reenter_mid:
                        entry_price = or_mid
                    else:
                        entry_price = or_low
                    
                    if abs(bar_close - entry_price) / entry_price < 0.002:
                        signal = self._create_fade_signal(
                            direction="long",
                            entry_price=entry_price,
                            or_high=or_high,
                            or_low=or_low,
                            failure_extreme=bar_low,
                            context=context,
                        )
                        signals.append(signal)
                        logger.info(f"Failure fade LONG detected: wick {wick_ratio:.2f}, vol {volume_ratio:.2f}")
        
        return signals
    
    def _create_fade_signal(
        self,
        direction: str,
        entry_price: float,
        or_high: float,
        or_low: float,
        failure_extreme: float,
        context: Dict,
    ) -> CandidateSignal:
        """Create failure fade signal.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            or_high: OR high
            or_low: OR low
            failure_extreme: Failed breakout extreme
            context: Market context
            
        Returns:
            CandidateSignal
        """
        # Stop just outside failure extreme
        buffer = context.get("atr_14", 1.0) * 0.1  # Small buffer
        if direction == "long":
            initial_stop = failure_extreme - buffer
        else:  # short
            initial_stop = failure_extreme + buffer
        
        phase1_distance = abs(entry_price - initial_stop)
        
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
        
        # Exit mode: Single target with time stop
        exit_mode = ExitModeDescriptor(
            mode=ExitMode.SINGLE_TARGET,
            time_limit_minutes=self.time_stop_minutes,
        )
        
        signal = CandidateSignal(
            playbook_name=self.name,
            direction=direction,
            entry_price=entry_price,
            trigger_price=entry_price,
            buffer_used=0.0,
            initial_stop=initial_stop,
            phase1_stop_distance=phase1_distance,
            structural_anchor=failure_extreme,
            exit_mode=exit_mode,
            metadata=metadata,
            timestamp=context["timestamp"],
            priority=1.2,  # Higher priority than basic ORB
        )
        
        return signal
    
    def preferred_exit_mode(self, context: Dict) -> ExitModeDescriptor:
        """Preferred exit mode for failure fade.
        
        Args:
            context: Market context
            
        Returns:
            ExitModeDescriptor
        """
        return ExitModeDescriptor(
            mode=ExitMode.SINGLE_TARGET,
            time_limit_minutes=self.time_stop_minutes,
        )
    
    def reset_session(self):
        """Reset per-session state."""
        self.failed_breakout_high = None
        self.failed_breakout_low = None
        self.failure_detected = False

