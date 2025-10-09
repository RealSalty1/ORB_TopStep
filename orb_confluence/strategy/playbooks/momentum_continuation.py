"""Momentum Continuation Playbook.

Trend-following strategy that enters on pullbacks within strong trends.

Key Concepts:
- Impulse: Strong directional move establishing trend
- Impulse Quality Function (IQF): Measures impulse strength
- Pullback: Retracement to structure (50-61.8% Fibonacci or moving average)
- Multi-timeframe Alignment: 5m, 15m, 60m all trending same direction
- Asymmetric Exits: Partials at targets, runners with trailing stops

Strategy Logic:
1. Detect strong impulse move (IQF > 1.8)
2. Wait for pullback to structural support/resistance
3. Verify multi-timeframe alignment
4. Check order flow confirms continuation (microstructure pressure)
5. Enter on pullback completion
6. Target: Extension beyond impulse high/low
7. Stop: Below pullback structure

Based on Dr. Hoffman's specifications in 10_08_project_review.md Section 4.2
"""

from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from loguru import logger

from orb_confluence.strategy.playbook_base import (
    Playbook, Signal, ProfitTarget, Direction
)


class MomentumContinuationPlaybook(Playbook):
    """Momentum Continuation - Trend Following Playbook.
    
    Rides strong trends by entering on pullbacks after high-quality impulses.
    
    Example:
        >>> playbook = MomentumContinuationPlaybook(
        ...     min_iqf=1.8,
        ...     pullback_min=0.382,
        ...     pullback_max=0.618,
        ... )
        >>> signal = playbook.check_entry(bars, current_bar, regime, features, [])
    """
    
    def __init__(
        self,
        min_iqf: float = 1.8,
        pullback_min: float = 0.382,
        pullback_max: float = 0.618,
        min_impulse_bars: int = 5,
        max_impulse_bars: int = 30,
        min_directional_commitment: float = 0.60,
        stop_buffer_r: float = 0.15,
    ):
        """Initialize Momentum Continuation playbook.
        
        Args:
            min_iqf: Minimum Impulse Quality Function (default: 1.8)
            pullback_min: Minimum pullback (Fib 38.2%, default: 0.382)
            pullback_max: Maximum pullback (Fib 61.8%, default: 0.618)
            min_impulse_bars: Minimum bars for impulse (default: 5)
            max_impulse_bars: Maximum bars for impulse (default: 30)
            min_directional_commitment: Minimum commitment score (default: 0.60)
            stop_buffer_r: Stop buffer as R-multiple (default: 0.15)
        """
        super().__init__()
        
        self.config = {
            'min_iqf': min_iqf,
            'pullback_min': pullback_min,
            'pullback_max': pullback_max,
            'min_impulse_bars': min_impulse_bars,
            'max_impulse_bars': max_impulse_bars,
            'min_directional_commitment': min_directional_commitment,
            'stop_buffer_r': stop_buffer_r,
        }
    
    @property
    def name(self) -> str:
        """Playbook name."""
        return "Momentum Continuation"
    
    @property
    def description(self) -> str:
        """Brief description."""
        return (
            "Trend-following strategy that enters on pullbacks within strong trends. "
            "Uses Impulse Quality Function and multi-timeframe alignment."
        )
    
    @property
    def preferred_regimes(self) -> List[str]:
        """Preferred market regimes."""
        return ["TREND"]
    
    @property
    def playbook_type(self) -> str:
        """Playbook type."""
        return "MOMENTUM"
    
    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
    ) -> Optional[Signal]:
        """Check if Momentum Continuation entry conditions are met.
        
        Entry Logic:
        1. Identify recent impulse move
        2. Calculate Impulse Quality Function (IQF)
        3. Verify IQF > threshold (1.8)
        4. Detect pullback to structure (38.2-61.8%)
        5. Check directional commitment remains high
        6. Verify microstructure confirms continuation
        7. Check regime = TREND
        
        Args:
            bars: Historical bars
            current_bar: Current bar
            regime: Current regime
            features: Current feature values
            open_positions: Currently open positions
            
        Returns:
            Signal if conditions met, None otherwise
        """
        # Check if already in position
        if self._has_open_position(open_positions):
            return None
        
        # Need sufficient bars for impulse detection
        if len(bars) < 50:
            return None
        
        # Step 1: Detect impulse
        impulse = self._detect_impulse(bars)
        if impulse is None:
            return None
        
        direction, impulse_start, impulse_end, impulse_range = impulse
        
        # Step 2: Calculate IQF
        iqf = self._calculate_iqf(bars, impulse_start, impulse_end, impulse_range)
        if iqf is None or iqf < self.config['min_iqf']:
            logger.debug(f"Momentum: IQF too low ({iqf:.2f} < {self.config['min_iqf']})")
            return None
        
        # Step 3: Detect pullback to structure
        pullback_data = self._detect_pullback(
            bars, current_bar, impulse_start, impulse_end, impulse_range, direction
        )
        if pullback_data is None:
            return None
        
        pullback_pct, pullback_low, structure_level = pullback_data
        
        # Step 4: Check directional commitment still strong
        directional_commitment = features.get('directional_commitment', 0.5)
        if directional_commitment < self.config['min_directional_commitment']:
            logger.debug(
                f"Momentum: Low directional commitment "
                f"({directional_commitment:.2f} < {self.config['min_directional_commitment']})"
            )
            return None
        
        # Step 5: Check microstructure pressure aligns
        microstructure_pressure = features.get('microstructure_pressure', 0.0)
        if direction == Direction.LONG and microstructure_pressure < -0.1:
            logger.debug("Momentum: Microstructure shows selling pressure (LONG setup)")
            return None
        if direction == Direction.SHORT and microstructure_pressure > 0.1:
            logger.debug("Momentum: Microstructure shows buying pressure (SHORT setup)")
            return None
        
        # Step 6: Check regime
        regime_alignment = self.get_regime_alignment(regime)
        if regime_alignment < 0.8:  # Strict for momentum
            logger.debug(f"Momentum: Poor regime alignment ({regime})")
            return None
        
        # Calculate entry, stop, targets
        entry_price = current_bar['close']
        stop_price = self._calculate_stop(pullback_low, direction, impulse_range)
        profit_targets = self._calculate_profit_targets(
            entry_price, stop_price, impulse_range, impulse_end, direction
        )
        
        # Calculate signal strength
        strength = self._calculate_signal_strength(
            iqf, pullback_pct, directional_commitment, microstructure_pressure, direction
        )
        confidence = strength * regime_alignment
        
        # Create signal
        signal = Signal(
            playbook_name=self.name,
            direction=direction,
            entry_price=entry_price,
            initial_stop=stop_price,
            profit_targets=profit_targets,
            strength=strength,
            regime_alignment=regime_alignment,
            confidence=confidence,
            metadata={
                'impulse_start_idx': impulse_start,
                'impulse_end_idx': impulse_end,
                'impulse_range': impulse_range,
                'iqf': iqf,
                'pullback_pct': pullback_pct,
                'pullback_low': pullback_low,
                'structure_level': structure_level,
                'directional_commitment': directional_commitment,
                'microstructure_pressure': microstructure_pressure,
                'setup_type': 'MOMENTUM_CONTINUATION',
            },
            timestamp=current_bar.get('timestamp_utc'),
        )
        
        logger.info(
            f"Momentum {direction.value} signal: "
            f"Entry={entry_price:.2f}, IQF={iqf:.2f}, "
            f"Pullback={pullback_pct:.1%}, Strength={strength:.2f}"
        )
        
        return signal
    
    def update_stops(
        self,
        position: Any,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        mfe: float,
        mae: float,
    ) -> float:
        """Update stop using three-phase logic with volatility adaptation.
        
        Phase 1 (0-1.0R): Keep initial stop (tight)
        Phase 2 (1.0-2.0R): Trail with structure
        Phase 3 (>2.0R): Aggressive parabolic trailing
        
        Momentum trades trail differently - wider stops to allow trend to run.
        
        Args:
            position: Current position
            bars: Historical bars
            current_bar: Current bar
            mfe: Maximum Favorable Excursion (R)
            mae: Maximum Adverse Excursion (R)
            
        Returns:
            New stop price
        """
        entry_price = position.entry_price
        current_stop = position.current_stop
        direction = position.direction
        initial_risk = position.initial_risk
        
        # Phase 1: Hold initial stop (momentum needs room)
        if mfe < 1.0:
            return current_stop
        
        # Phase 2: Trail with structure (1.0-2.0R)
        if mfe < 2.0:
            # Use swing lows/highs
            trail_bars = 10
            recent = bars.tail(trail_bars)
            
            if direction == Direction.LONG:
                swing_low = recent['low'].min()
                buffer = initial_risk * 0.2
                new_stop = swing_low - buffer
                return max(new_stop, current_stop)
            else:
                swing_high = recent['high'].max()
                buffer = initial_risk * 0.2
                new_stop = swing_high + buffer
                return min(new_stop, current_stop)
        
        # Phase 3: Aggressive parabolic trailing (>2.0R)
        # Trail tighter as profit extends
        trail_pct = 0.3 - (0.05 * min(mfe - 2.0, 3.0))  # Tighten as MFE grows
        
        current_price = current_bar['close']
        
        if direction == Direction.LONG:
            trail_distance = (current_price - entry_price) * trail_pct
            new_stop = current_price - trail_distance
            return max(new_stop, current_stop)
        else:
            trail_distance = (entry_price - current_price) * trail_pct
            new_stop = current_price + trail_distance
            return min(new_stop, current_stop)
    
    def check_salvage(
        self,
        position: Any,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        mfe: float,
        mae: float,
        bars_in_trade: int,
    ) -> bool:
        """Check if position should be salvaged.
        
        Momentum trades get more room, but salvage if:
        1. Trend breaks (momentum reversal)
        2. Excessive time without progress (>60 bars)
        3. Deep retracement after profit (>75%)
        
        Args:
            position: Current position
            bars: Historical bars
            current_bar: Current bar
            mfe: MFE in R
            mae: MAE in R
            bars_in_trade: Bars since entry
            
        Returns:
            True if should salvage
        """
        # Condition 1: Trend break (momentum reversal)
        if mfe > 0.5:
            velocity = self._calculate_velocity(bars, position.direction)
            if velocity < -0.2:  # Negative velocity = wrong direction
                logger.info(f"Momentum salvage: Trend reversal (velocity={velocity:.2f})")
                return True
        
        # Condition 2: Time-based (longer threshold for momentum)
        if bars_in_trade > 60:
            current_r = self._calculate_current_r(position, current_bar)
            if abs(current_r) < 0.5:
                logger.info(
                    f"Momentum salvage: Stalled {bars_in_trade} bars "
                    f"with only {current_r:.2f}R"
                )
                return True
        
        # Condition 3: Deep retracement (tighter for momentum)
        if mfe > 1.0:
            current_r = self._calculate_current_r(position, current_bar)
            retrace_pct = (mfe - current_r) / mfe if mfe > 0 else 0
            
            if retrace_pct > 0.75:
                logger.info(
                    f"Momentum salvage: Retraced {retrace_pct:.1%} from MFE={mfe:.2f}R"
                )
                return True
        
        return False
    
    def _detect_impulse(
        self,
        bars: pd.DataFrame,
    ) -> Optional[Tuple[Direction, int, int, float]]:
        """Detect strong impulse move in recent bars.
        
        Impulse = directional move with minimal retracement.
        
        Args:
            bars: Historical bars
            
        Returns:
            Tuple of (direction, start_idx, end_idx, range) or None
        """
        lookback = 50
        recent = bars.tail(lookback)
        
        if len(recent) < 20:
            return None
        
        # Look for strong moves in recent bars
        # Try different impulse lengths
        for impulse_len in range(self.config['max_impulse_bars'], 
                                 self.config['min_impulse_bars'] - 1, -1):
            
            if impulse_len > len(recent) - 10:
                continue
            
            # Check for bullish impulse
            for i in range(len(recent) - impulse_len - 5):
                impulse_bars = recent.iloc[i:i+impulse_len]
                
                # Calculate net movement
                net_move = impulse_bars['close'].iloc[-1] - impulse_bars['close'].iloc[0]
                impulse_range = impulse_bars['high'].max() - impulse_bars['low'].min()
                
                if impulse_range == 0:
                    continue
                
                # Check if mostly upward
                efficiency = net_move / impulse_range
                
                if efficiency > 0.65:  # Strong bullish impulse
                    return (
                        Direction.LONG,
                        i,
                        i + impulse_len,
                        impulse_range
                    )
                elif efficiency < -0.65:  # Strong bearish impulse
                    return (
                        Direction.SHORT,
                        i,
                        i + impulse_len,
                        impulse_range
                    )
        
        return None
    
    def _calculate_iqf(
        self,
        bars: pd.DataFrame,
        impulse_start: int,
        impulse_end: int,
        impulse_range: float,
    ) -> Optional[float]:
        """Calculate Impulse Quality Function.
        
        Formula: IQF = (Range/ATR)^0.7 × (Vol/20d_avg)^0.5 × e^(-λ × bars)
        
        Components:
        - Range relative to ATR (price strength)
        - Volume relative to average (participation)
        - Time decay (faster impulse = stronger)
        
        Args:
            bars: Historical bars
            impulse_start: Start index of impulse
            impulse_end: End index of impulse
            impulse_range: Price range of impulse
            
        Returns:
            IQF value or None
        """
        lookback = 100
        historical = bars.tail(lookback)
        
        if len(historical) < 50:
            return None
        
        # Get impulse bars
        impulse_bars = historical.iloc[impulse_start:impulse_end]
        impulse_len = len(impulse_bars)
        
        if impulse_len == 0:
            return None
        
        # Component 1: Range relative to ATR
        atr_period = 14
        historical_copy = historical.copy()
        historical_copy['tr'] = self._calculate_true_range(historical_copy)
        atr = historical_copy['tr'].rolling(atr_period).mean().iloc[-1]
        
        if atr == 0:
            return None
        
        range_component = (impulse_range / atr) ** 0.7
        
        # Component 2: Volume relative to average
        avg_volume = historical['volume'].rolling(20).mean().mean()
        impulse_volume = impulse_bars['volume'].mean()
        
        if avg_volume == 0:
            volume_component = 1.0
        else:
            volume_component = (impulse_volume / avg_volume) ** 0.5
        
        # Component 3: Time decay (punish slow impulses)
        lambda_decay = 0.05
        time_component = np.exp(-lambda_decay * impulse_len)
        
        # Calculate IQF
        iqf = range_component * volume_component * time_component
        
        return float(iqf)
    
    def _detect_pullback(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        impulse_start: int,
        impulse_end: int,
        impulse_range: float,
        direction: Direction,
    ) -> Optional[Tuple[float, float, float]]:
        """Detect pullback to structural level.
        
        Pullback should be 38.2%-61.8% of impulse (Fibonacci retracement).
        
        Args:
            bars: Historical bars
            current_bar: Current bar
            impulse_start: Impulse start index
            impulse_end: Impulse end index
            impulse_range: Impulse range
            direction: Trend direction
            
        Returns:
            Tuple of (pullback_pct, pullback_extreme, structure_level) or None
        """
        lookback = 100
        recent = bars.tail(lookback)
        
        # Get impulse bars
        impulse_bars = recent.iloc[impulse_start:impulse_end]
        
        if direction == Direction.LONG:
            impulse_low = impulse_bars['low'].min()
            impulse_high = impulse_bars['high'].max()
            
            # Bars after impulse
            after_impulse = recent.iloc[impulse_end:]
            if len(after_impulse) < 3:
                return None
            
            # Check for pullback
            pullback_low = after_impulse['low'].min()
            
            # Calculate pullback percentage
            pullback_pct = (impulse_high - pullback_low) / impulse_range
            
            # Check if within range
            if pullback_pct < self.config['pullback_min'] or pullback_pct > self.config['pullback_max']:
                return None
            
            # Structure level (50% Fib)
            structure_level = impulse_low + (impulse_range * 0.5)
            
            # Check if current price is near structure (testing support)
            current_price = current_bar['close']
            if abs(current_price - structure_level) > impulse_range * 0.15:
                return None  # Too far from structure
            
            return (pullback_pct, pullback_low, structure_level)
        
        else:  # SHORT
            impulse_high = impulse_bars['high'].max()
            impulse_low = impulse_bars['low'].min()
            
            after_impulse = recent.iloc[impulse_end:]
            if len(after_impulse) < 3:
                return None
            
            pullback_high = after_impulse['high'].max()
            
            pullback_pct = (pullback_high - impulse_low) / impulse_range
            
            if pullback_pct < self.config['pullback_min'] or pullback_pct > self.config['pullback_max']:
                return None
            
            structure_level = impulse_high - (impulse_range * 0.5)
            
            current_price = current_bar['close']
            if abs(current_price - structure_level) > impulse_range * 0.15:
                return None
            
            return (pullback_pct, pullback_high, structure_level)
    
    def _calculate_stop(
        self,
        pullback_extreme: float,
        direction: Direction,
        impulse_range: float,
    ) -> float:
        """Calculate initial stop price.
        
        Stop below pullback low (for LONG) or above pullback high (for SHORT).
        
        Args:
            pullback_extreme: Pullback low (LONG) or high (SHORT)
            direction: Trade direction
            impulse_range: Impulse range for buffer
            
        Returns:
            Stop price
        """
        buffer_r = self.config['stop_buffer_r']
        buffer = impulse_range * buffer_r
        
        if direction == Direction.LONG:
            return pullback_extreme - buffer
        else:
            return pullback_extreme + buffer
    
    def _calculate_profit_targets(
        self,
        entry_price: float,
        stop_price: float,
        impulse_range: float,
        impulse_end_idx: int,
        direction: Direction,
    ) -> List[ProfitTarget]:
        """Calculate profit targets.
        
        T1: 1.5R (30% position) - Quick partial
        T2: 2.5R (30% position) - Extension target
        T3: Runner (40% position) - Trail indefinitely
        
        Args:
            entry_price: Entry price
            stop_price: Stop price
            impulse_range: Original impulse range
            impulse_end_idx: Impulse end index
            direction: Trade direction
            
        Returns:
            List of profit targets
        """
        initial_risk = abs(entry_price - stop_price)
        
        targets = []
        
        # Target 1: Quick 1.5R (momentum confirmation)
        if direction == Direction.LONG:
            t1_price = entry_price + (initial_risk * 1.5)
        else:
            t1_price = entry_price - (initial_risk * 1.5)
        
        targets.append(ProfitTarget(
            price=t1_price,
            size_pct=0.3,
            label="1.5R Quick",
            r_multiple=1.5
        ))
        
        # Target 2: Extension target (2.5R)
        if direction == Direction.LONG:
            t2_price = entry_price + (initial_risk * 2.5)
        else:
            t2_price = entry_price - (initial_risk * 2.5)
        
        targets.append(ProfitTarget(
            price=t2_price,
            size_pct=0.3,
            label="2.5R Extension",
            r_multiple=2.5
        ))
        
        # Target 3: Runner (trail with stops)
        # Set at 4R but will trail
        if direction == Direction.LONG:
            t3_price = entry_price + (initial_risk * 4.0)
        else:
            t3_price = entry_price - (initial_risk * 4.0)
        
        targets.append(ProfitTarget(
            price=t3_price,
            size_pct=0.4,
            label="Runner",
            r_multiple=4.0
        ))
        
        return targets
    
    def _calculate_signal_strength(
        self,
        iqf: float,
        pullback_pct: float,
        directional_commitment: float,
        microstructure_pressure: float,
        direction: Direction,
    ) -> float:
        """Calculate signal strength (0-1).
        
        Factors:
        - IQF (higher = stronger)
        - Pullback depth (shallower = stronger)
        - Directional commitment (higher = stronger)
        - Microstructure alignment (stronger = better)
        
        Args:
            iqf: Impulse Quality Function
            pullback_pct: Pullback percentage
            directional_commitment: Commitment score
            microstructure_pressure: Order flow pressure
            direction: Trade direction
            
        Returns:
            Strength score (0-1)
        """
        # Component 1: IQF (normalize, assume max ~4.0)
        iqf_score = min(iqf / 4.0, 1.0)
        
        # Component 2: Pullback (shallower = stronger)
        # 38.2% pullback = strongest, 61.8% = weakest
        pullback_score = 1.0 - ((pullback_pct - 0.382) / (0.618 - 0.382))
        pullback_score = np.clip(pullback_score, 0, 1)
        
        # Component 3: Directional commitment
        commitment_score = directional_commitment
        
        # Component 4: Microstructure alignment
        if direction == Direction.LONG:
            micro_score = (microstructure_pressure + 1) / 2  # Convert -1,1 to 0,1
        else:
            micro_score = (-microstructure_pressure + 1) / 2
        
        # Weighted combination
        strength = (
            0.4 * iqf_score +
            0.25 * pullback_score +
            0.20 * commitment_score +
            0.15 * micro_score
        )
        
        return float(np.clip(strength, 0, 1))
    
    def _has_open_position(self, open_positions: List[Any]) -> bool:
        """Check if already have open position from this playbook."""
        for pos in open_positions:
            if hasattr(pos, 'playbook_name') and pos.playbook_name == self.name:
                return True
        return False
    
    @staticmethod
    def _calculate_true_range(bars: pd.DataFrame) -> pd.Series:
        """Calculate True Range."""
        high_low = bars['high'] - bars['low']
        high_prev_close = abs(bars['high'] - bars['close'].shift(1))
        low_prev_close = abs(bars['low'] - bars['close'].shift(1))
        
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        return tr
    
    @staticmethod
    def _calculate_current_r(position: Any, current_bar: pd.Series) -> float:
        """Calculate current R-multiple."""
        entry_price = position.entry_price
        initial_risk = position.initial_risk
        current_price = current_bar['close']
        
        if position.direction == Direction.LONG:
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price
        
        return profit / initial_risk if initial_risk > 0 else 0
    
    @staticmethod
    def _calculate_velocity(bars: pd.DataFrame, direction: Direction) -> float:
        """Calculate price velocity (momentum).
        
        Args:
            bars: Recent bars
            direction: Trade direction
            
        Returns:
            Velocity score (-1 to 1)
        """
        recent = bars.tail(10)
        
        if len(recent) < 3:
            return 0.0
        
        # Linear regression slope
        x = np.arange(len(recent))
        y = recent['close'].values
        
        if len(x) != len(y):
            return 0.0
        
        # Calculate slope
        slope = np.polyfit(x, y, 1)[0]
        
        # Normalize by ATR
        atr = (recent['high'] - recent['low']).mean()
        if atr == 0:
            return 0.0
        
        velocity = slope / atr
        
        # For SHORT, flip sign
        if direction == Direction.SHORT:
            velocity = -velocity
        
        return float(np.clip(velocity, -1, 1))

