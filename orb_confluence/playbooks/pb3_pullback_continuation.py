"""PB3: Pullback Continuation - Trade post-impulse flags.

Logic:
1. Detect strong impulse move (MFE >= threshold within time limit)
2. Wait for orderly pullback (bull/bear flag or VWAP retest)
3. Enter on continuation break of flag
4. Trail structural pivots
5. Abort if flag consolidation loses momentum
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


class PullbackContinuationPlaybook(Playbook):
    """Pullback Continuation playbook.
    
    Configuration:
    - impulse_threshold_r: Min MFE to qualify as impulse (e.g., 0.8R)
    - impulse_time_bars: Max bars to achieve impulse (e.g., 15)
    - flag_min_bars: Min bars for flag formation (e.g., 3)
    - flag_max_bars: Max bars before momentum lost (e.g., 20)
    - flag_retrace_min: Min retrace % of impulse (e.g., 0.25)
    - flag_retrace_max: Max retrace % of impulse (e.g., 0.62)
    
    Example:
        >>> playbook = PullbackContinuationPlaybook(config={
        ...     "impulse_threshold_r": 0.8,
        ...     "impulse_time_bars": 15,
        ...     "flag_min_bars": 3,
        ...     "flag_max_bars": 20
        ... })
    """
    
    def __init__(
        self,
        name: str = "PB3_Pullback_Continuation",
        config: Optional[Dict] = None
    ) -> None:
        """Initialize Pullback Continuation playbook."""
        super().__init__(name, config)
        
        self.impulse_threshold_r = self.config.get("impulse_threshold_r", 0.8)
        self.impulse_time_bars = self.config.get("impulse_time_bars", 15)
        self.flag_min_bars = self.config.get("flag_min_bars", 3)
        self.flag_max_bars = self.config.get("flag_max_bars", 20)
        self.flag_retrace_min = self.config.get("flag_retrace_min", 0.25)
        self.flag_retrace_max = self.config.get("flag_retrace_max", 0.62)
        
        # State tracking
        self.impulse_detected = False
        self.impulse_direction: Optional[str] = None
        self.impulse_high: Optional[float] = None
        self.impulse_low: Optional[float] = None
        self.impulse_bar_count = 0
        self.flag_bar_count = 0
        self.flag_high: Optional[float] = None
        self.flag_low: Optional[float] = None
    
    def is_eligible(self, context: Dict) -> bool:
        """Check eligibility for pullback continuation.
        
        Eligible if:
        - OR finalized
        - Either impulse detected OR looking for impulse
        
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
        
        return True
    
    def generate_signals(self, context: Dict) -> List[CandidateSignal]:
        """Generate pullback continuation signals.
        
        Logic flow:
        1. Detect impulse (if not already detected)
        2. Track flag formation
        3. Signal on flag breakout
        
        Args:
            context: Market context
            
        Returns:
            List of CandidateSignal (0-1)
        """
        signals = []
        
        # Get bar data
        current_bar = context.get("current_bar")
        if current_bar is None:
            return signals
        
        current_price = current_bar["close"]
        or_high = context["or_primary_high"]
        or_low = context["or_primary_low"]
        
        # Step 1: Detect impulse if not already
        if not self.impulse_detected:
            self._check_for_impulse(context, current_bar)
            return signals  # Don't signal same bar as impulse
        
        # Step 2: Track flag formation
        if self.impulse_detected:
            self.flag_bar_count += 1
            
            # Update flag high/low
            if self.flag_high is None:
                self.flag_high = current_bar["high"]
                self.flag_low = current_bar["low"]
            else:
                self.flag_high = max(self.flag_high, current_bar["high"])
                self.flag_low = min(self.flag_low, current_bar["low"])
            
            # Check if flag too long (momentum lost)
            if self.flag_bar_count > self.flag_max_bars:
                logger.debug(f"Pullback continuation: flag too long ({self.flag_bar_count} bars), resetting")
                self._reset_state()
                return signals
            
            # Check if flag has minimum bars
            if self.flag_bar_count < self.flag_min_bars:
                return signals
            
            # Step 3: Check for continuation breakout
            if self.impulse_direction == "long":
                # Long continuation: break above flag high
                if current_price > self.flag_high:
                    # Validate retrace
                    impulse_range = self.impulse_high - or_high
                    flag_retrace = self.impulse_high - self.flag_low
                    retrace_pct = flag_retrace / impulse_range if impulse_range > 0 else 0.0
                    
                    if self.flag_retrace_min <= retrace_pct <= self.flag_retrace_max:
                        signal = self._create_continuation_signal(
                            direction="long",
                            entry_price=current_price,
                            flag_high=self.flag_high,
                            flag_low=self.flag_low,
                            context=context,
                        )
                        signals.append(signal)
                        logger.info(
                            f"Pullback continuation LONG: flag {self.flag_bar_count} bars, "
                            f"retrace {retrace_pct:.0%}"
                        )
                        self._reset_state()
            
            elif self.impulse_direction == "short":
                # Short continuation: break below flag low
                if current_price < self.flag_low:
                    impulse_range = or_low - self.impulse_low
                    flag_retrace = self.flag_high - self.impulse_low
                    retrace_pct = flag_retrace / impulse_range if impulse_range > 0 else 0.0
                    
                    if self.flag_retrace_min <= retrace_pct <= self.flag_retrace_max:
                        signal = self._create_continuation_signal(
                            direction="short",
                            entry_price=current_price,
                            flag_high=self.flag_high,
                            flag_low=self.flag_low,
                            context=context,
                        )
                        signals.append(signal)
                        logger.info(
                            f"Pullback continuation SHORT: flag {self.flag_bar_count} bars, "
                            f"retrace {retrace_pct:.0%}"
                        )
                        self._reset_state()
        
        return signals
    
    def _check_for_impulse(self, context: Dict, bar) -> None:
        """Check if impulse move detected.
        
        Args:
            context: Market context
            bar: Current bar
        """
        # Track bars since OR end
        breakout_delay = context.get("breakout_delay_minutes", 0)
        bars_since_or = int(breakout_delay)  # Approximate
        
        if bars_since_or > self.impulse_time_bars:
            return  # Too late for impulse
        
        # Check for strong move
        or_high = context["or_primary_high"]
        or_low = context["or_primary_low"]
        atr_14 = context.get("atr_14", 1.0)
        
        current_price = bar["close"]
        
        # Long impulse: strong move above OR
        if current_price > or_high:
            move_size = current_price - or_high
            move_r = move_size / atr_14 if atr_14 > 0 else 0.0
            
            if move_r >= self.impulse_threshold_r:
                self.impulse_detected = True
                self.impulse_direction = "long"
                self.impulse_high = bar["high"]
                self.impulse_bar_count = bars_since_or
                logger.debug(f"Impulse detected: LONG {move_r:.2f}R in {bars_since_or} bars")
        
        # Short impulse: strong move below OR
        elif current_price < or_low:
            move_size = or_low - current_price
            move_r = move_size / atr_14 if atr_14 > 0 else 0.0
            
            if move_r >= self.impulse_threshold_r:
                self.impulse_detected = True
                self.impulse_direction = "short"
                self.impulse_low = bar["low"]
                self.impulse_bar_count = bars_since_or
                logger.debug(f"Impulse detected: SHORT {move_r:.2f}R in {bars_since_or} bars")
    
    def _create_continuation_signal(
        self,
        direction: str,
        entry_price: float,
        flag_high: float,
        flag_low: float,
        context: Dict,
    ) -> CandidateSignal:
        """Create continuation signal.
        
        Args:
            direction: 'long' or 'short'
            entry_price: Entry price
            flag_high: Flag high
            flag_low: Flag low
            context: Market context
            
        Returns:
            CandidateSignal
        """
        # Stop below flag low (long) or above flag high (short)
        atr_14 = context.get("atr_14", 1.0)
        buffer = atr_14 * 0.15
        
        if direction == "long":
            initial_stop = flag_low - buffer
            structural_anchor = flag_low
        else:  # short
            initial_stop = flag_high + buffer
            structural_anchor = flag_high
        
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
        
        # Exit mode: Trail pivots (no early partial)
        exit_mode = ExitModeDescriptor(
            mode=ExitMode.TRAIL_PIVOT,
        )
        
        signal = CandidateSignal(
            playbook_name=self.name,
            direction=direction,
            entry_price=entry_price,
            trigger_price=entry_price,
            buffer_used=0.0,
            initial_stop=initial_stop,
            phase1_stop_distance=phase1_distance,
            structural_anchor=structural_anchor,
            exit_mode=exit_mode,
            metadata=metadata,
            timestamp=context["timestamp"],
            priority=1.1,  # Slightly higher than basic ORB
        )
        
        return signal
    
    def preferred_exit_mode(self, context: Dict) -> ExitModeDescriptor:
        """Preferred exit mode for pullback continuation.
        
        Args:
            context: Market context
            
        Returns:
            ExitModeDescriptor
        """
        return ExitModeDescriptor(
            mode=ExitMode.TRAIL_PIVOT,
        )
    
    def _reset_state(self):
        """Reset impulse/flag tracking."""
        self.impulse_detected = False
        self.impulse_direction = None
        self.impulse_high = None
        self.impulse_low = None
        self.impulse_bar_count = 0
        self.flag_bar_count = 0
        self.flag_high = None
        self.flag_low = None
    
    def reset_session(self):
        """Reset for new session."""
        self._reset_state()

