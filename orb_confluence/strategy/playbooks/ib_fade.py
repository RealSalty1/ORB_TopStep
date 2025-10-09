"""Initial Balance Fade Playbook.

Mean reversion strategy that fades extensions beyond the Initial Balance (first hour).

Key Concepts:
- Initial Balance (IB): First 60 minutes of trading
- Extension: Move beyond IB high/low
- Auction Efficiency Ratio (AER): Measures conviction of extension
- Acceptance Velocity: Speed of return toward IB after extension

Strategy Logic:
1. Wait for IB to form (first 60 minutes)
2. Detect extension beyond IB (e.g., 1.5x IB range or more)
3. Calculate AER - low AER (<0.65) indicates weak extension
4. Enter fade when price shows acceptance back toward IB
5. Target: IB midpoint or opposite extreme
6. Stop: Beyond recent extension extreme

Based on Dr. Hoffman's specifications in 10_08_project_review.md Section 4.1
"""

from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd
from loguru import logger

from orb_confluence.strategy.playbook_base import (
    Playbook, Signal, ProfitTarget, Direction
)


class IBFadePlaybook(Playbook):
    """Initial Balance Fade - Mean Reversion Playbook.
    
    Fades poor-conviction extensions beyond the Initial Balance.
    
    Example:
        >>> playbook = IBFadePlaybook(
        ...     ib_minutes=60,
        ...     extension_threshold=1.5,
        ...     max_aer=0.65,
        ... )
        >>> signal = playbook.check_entry(bars, current_bar, regime, features, [])
    """
    
    def __init__(
        self,
        ib_minutes: int = 60,
        extension_threshold: float = 1.5,
        min_extension_ticks: int = 8,
        max_aer: float = 0.65,
        min_acceptance_bars: int = 3,
        stop_buffer_r: float = 0.2,
    ):
        """Initialize IB Fade playbook.
        
        Args:
            ib_minutes: Minutes for Initial Balance (default: 60)
            extension_threshold: Minimum extension as multiple of IB range (default: 1.5)
            min_extension_ticks: Minimum extension in ticks (default: 8)
            max_aer: Maximum Auction Efficiency Ratio for entry (default: 0.65)
            min_acceptance_bars: Bars showing acceptance before entry (default: 3)
            stop_buffer_r: Additional buffer for stops as R-multiple (default: 0.2)
        """
        super().__init__()
        
        self.config = {
            'ib_minutes': ib_minutes,
            'extension_threshold': extension_threshold,
            'min_extension_ticks': min_extension_ticks,
            'max_aer': max_aer,
            'min_acceptance_bars': min_acceptance_bars,
            'stop_buffer_r': stop_buffer_r,
        }
        
        # Cache for IB calculations
        self._ib_cache: Dict[str, Any] = {}
    
    @property
    def name(self) -> str:
        """Playbook name."""
        return "Initial Balance Fade"
    
    @property
    def description(self) -> str:
        """Brief description."""
        return (
            "Fades weak extensions beyond the Initial Balance (first hour). "
            "Looks for low auction efficiency and acceptance back toward IB."
        )
    
    @property
    def preferred_regimes(self) -> List[str]:
        """Preferred market regimes."""
        return ["RANGE", "VOLATILE"]
    
    @property
    def playbook_type(self) -> str:
        """Playbook type."""
        return "MEAN_REVERSION"
    
    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
        mbp10_snapshot: Optional[Dict] = None,
    ) -> Optional[Signal]:
        """Check if IB Fade entry conditions are met.
        
        Entry Logic:
        1. IB must be established (>= ib_minutes)
        2. Price must have extended beyond IB
        3. Extension must meet minimum threshold
        4. AER must be low (weak conviction)
        5. Must show acceptance back toward IB
        
        Args:
            bars: Historical bars
            current_bar: Current bar
            regime: Current regime
            features: Current feature values
            open_positions: Currently open positions
            
        Returns:
            Signal if conditions met, None otherwise
        """
        # Check if already in a position from this playbook
        if self._has_open_position(open_positions):
            return None
        
        # Calculate IB if not cached
        ib = self._calculate_initial_balance(bars)
        if ib is None:
            return None
        
        # Check for extension
        extension = self._detect_extension(bars, current_bar, ib)
        if extension is None:
            return None
        
        direction, extension_price, extension_range = extension
        
        # Calculate Auction Efficiency Ratio
        aer = self._calculate_aer(bars, ib, extension_price, direction)
        if aer is None or aer > self.config['max_aer']:
            logger.debug(f"IB Fade: AER too high ({aer:.3f} > {self.config['max_aer']})")
            return None
        
        # Check for acceptance (price moving back toward IB)
        has_acceptance = self._check_acceptance(bars, current_bar, extension_price, direction)
        if not has_acceptance:
            return None
        
        # Check regime alignment
        regime_alignment = self.get_regime_alignment(regime)
        if regime_alignment < 0.5:
            logger.debug(f"IB Fade: Poor regime alignment ({regime}) - skipping")
            return None
        
        # Calculate entry, stop, and targets
        entry_price = current_bar['close']
        stop_price = self._calculate_stop(extension_price, direction, extension_range)
        profit_targets = self._calculate_profit_targets(
            entry_price, stop_price, ib, direction
        )
        
        # Calculate signal strength
        strength = self._calculate_signal_strength(aer, extension_range, ib, features)
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
                'ib_high': ib['high'],
                'ib_low': ib['low'],
                'ib_range': ib['range'],
                'extension_price': extension_price,
                'extension_range': extension_range,
                'aer': aer,
                'setup_type': 'IB_FADE',
            },
            timestamp=current_bar.get('timestamp_utc'),
        )
        
        logger.info(
            f"IB Fade {direction.value} signal generated: "
            f"Entry={entry_price:.2f}, Stop={stop_price:.2f}, "
            f"AER={aer:.3f}, Strength={strength:.2f}"
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
        """Update stop using three-phase logic.
        
        Phase 1 (0-0.5R MFE): Keep initial stop
        Phase 2 (0.5-1.25R MFE): Move to breakeven
        Phase 3 (>1.25R MFE): Trail with structure
        
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
        
        # Phase 1: No stop adjustment (0 - 0.5R)
        if mfe < 0.5:
            return current_stop
        
        # Phase 2: Move to breakeven (0.5 - 1.25R)
        if mfe < 1.25:
            if direction == Direction.LONG:
                new_stop = entry_price + (initial_risk * 0.1)  # Small profit lock
            else:
                new_stop = entry_price - (initial_risk * 0.1)
            
            # Only tighten, never widen
            if direction == Direction.LONG:
                return max(new_stop, current_stop)
            else:
                return min(new_stop, current_stop)
        
        # Phase 3: Aggressive trailing (>1.25R)
        # Trail using recent swing low/high
        trail_bars = 5
        recent_bars = bars.tail(trail_bars)
        
        if direction == Direction.LONG:
            swing_low = recent_bars['low'].min()
            buffer = initial_risk * 0.15
            new_stop = swing_low - buffer
            return max(new_stop, current_stop)
        else:
            swing_high = recent_bars['high'].max()
            buffer = initial_risk * 0.15
            new_stop = swing_high + buffer
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
        
        Salvage Conditions:
        1. Retraced >70% of MFE after reaching 0.5R+
        2. Been in trade >45 bars with minimal movement
        3. Velocity decay (losing momentum toward target)
        
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
        # Condition 1: Deep retracement after profit
        if mfe > 0.5:
            current_r = self._calculate_current_r(position, current_bar)
            retrace_pct = (mfe - current_r) / mfe if mfe > 0 else 0
            
            if retrace_pct > 0.70:
                logger.info(
                    f"IB Fade salvage: Retraced {retrace_pct:.1%} from MFE "
                    f"(MFE={mfe:.2f}R, Current={current_r:.2f}R)"
                )
                return True
        
        # Condition 2: Time-based (stalling)
        if bars_in_trade > 45:
            current_r = self._calculate_current_r(position, current_bar)
            if abs(current_r) < 0.3:
                logger.info(
                    f"IB Fade salvage: Stalled for {bars_in_trade} bars "
                    f"with only {current_r:.2f}R movement"
                )
                return True
        
        # Condition 3: Velocity decay
        if mfe > 0.3:
            velocity = self._calculate_velocity(bars, position.direction)
            if velocity < 0.1:  # Very slow movement
                logger.info(
                    f"IB Fade salvage: Velocity decay ({velocity:.3f}) - "
                    f"losing momentum toward target"
                )
                return True
        
        return False
    
    def _calculate_initial_balance(self, bars: pd.DataFrame) -> Optional[Dict[str, float]]:
        """Calculate Initial Balance (first N minutes).
        
        Args:
            bars: Historical bars
            
        Returns:
            Dict with IB high, low, midpoint, range, or None if insufficient data
        """
        ib_minutes = self.config['ib_minutes']
        
        if len(bars) < ib_minutes:
            return None
        
        # Get first N minutes
        ib_bars = bars.head(ib_minutes)
        
        ib_high = ib_bars['high'].max()
        ib_low = ib_bars['low'].min()
        ib_range = ib_high - ib_low
        ib_midpoint = (ib_high + ib_low) / 2
        
        if ib_range == 0:
            logger.warning("IB range is zero")
            return None
        
        return {
            'high': ib_high,
            'low': ib_low,
            'range': ib_range,
            'midpoint': ib_midpoint,
        }
    
    def _detect_extension(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        ib: Dict[str, float],
    ) -> Optional[tuple]:
        """Detect if price has extended beyond IB.
        
        Args:
            bars: Historical bars
            current_bar: Current bar
            ib: Initial Balance dict
            
        Returns:
            Tuple of (direction, extension_price, extension_range) or None
        """
        # Look for extension in bars after IB formation
        ib_minutes = self.config['ib_minutes']
        extension_bars = bars.iloc[ib_minutes:]
        
        if len(extension_bars) < 5:
            return None
        
        # Check for upside extension
        extension_high = extension_bars['high'].max()
        upside_extension = extension_high - ib['high']
        
        # Check for downside extension
        extension_low = extension_bars['low'].min()
        downside_extension = ib['low'] - extension_low
        
        min_extension_ticks = self.config['min_extension_ticks']
        min_extension_points = min_extension_ticks * 0.25  # ES tick = 0.25
        
        # Check thresholds
        extension_threshold = self.config['extension_threshold']
        
        if upside_extension > ib['range'] * extension_threshold and upside_extension > min_extension_points:
            return (Direction.SHORT, extension_high, upside_extension)
        
        if downside_extension > ib['range'] * extension_threshold and downside_extension > min_extension_points:
            return (Direction.LONG, extension_low, downside_extension)
        
        return None
    
    def _calculate_aer(
        self,
        bars: pd.DataFrame,
        ib: Dict[str, float],
        extension_price: float,
        direction: Direction,
    ) -> Optional[float]:
        """Calculate Auction Efficiency Ratio.
        
        AER = (Extension Range) / (Sum of TRs during extension) × 
              (Extension Volume) / (IB Volume/minute × Extension Minutes)
        
        Low AER (<0.65) indicates poor conviction extension.
        
        Args:
            bars: Historical bars
            ib: Initial Balance dict
            extension_price: Price of extension extreme
            direction: Direction of extension
            
        Returns:
            AER value or None
        """
        ib_minutes = self.config['ib_minutes']
        ib_bars = bars.head(ib_minutes)
        extension_bars = bars.iloc[ib_minutes:]
        
        if len(extension_bars) < 3:
            return None
        
        # Find bars that formed the extension
        if direction == Direction.SHORT:
            # Upside extension
            extension_sequence = extension_bars[extension_bars['high'] >= ib['high']]
        else:
            # Downside extension
            extension_sequence = extension_bars[extension_bars['low'] <= ib['low']]
        
        if len(extension_sequence) == 0:
            return None
        
        # Calculate components
        if direction == Direction.SHORT:
            extension_range = extension_price - ib['high']
        else:
            extension_range = ib['low'] - extension_price
        
        # Sum of true ranges during extension
        extension_sequence = extension_sequence.copy()
        extension_sequence['tr'] = self._calculate_true_range(extension_sequence)
        sum_tr = extension_sequence['tr'].sum()
        
        if sum_tr == 0:
            return None
        
        # Volume ratio
        extension_volume = extension_sequence['volume'].sum()
        ib_volume_per_minute = ib_bars['volume'].mean()
        extension_minutes = len(extension_sequence)
        expected_volume = ib_volume_per_minute * extension_minutes
        
        if expected_volume == 0:
            volume_ratio = 1.0
        else:
            volume_ratio = extension_volume / expected_volume
        
        # Calculate AER
        aer = (extension_range / sum_tr) * volume_ratio
        
        return float(aer)
    
    @staticmethod
    def _calculate_true_range(bars: pd.DataFrame) -> pd.Series:
        """Calculate True Range."""
        high_low = bars['high'] - bars['low']
        high_prev_close = abs(bars['high'] - bars['close'].shift(1))
        low_prev_close = abs(bars['low'] - bars['close'].shift(1))
        
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        return tr
    
    def _check_acceptance(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        extension_price: float,
        direction: Direction,
    ) -> bool:
        """Check if price is showing acceptance back toward IB.
        
        Acceptance = price moving back from extension extreme.
        
        Args:
            bars: Historical bars
            current_bar: Current bar
            extension_price: Extension extreme price
            direction: Fade direction
            
        Returns:
            True if acceptance detected
        """
        min_bars = self.config['min_acceptance_bars']
        recent_bars = bars.tail(min_bars)
        
        if len(recent_bars) < min_bars:
            return False
        
        if direction == Direction.SHORT:
            # For upside extension, need to see closes below extension high
            acceptance_count = (recent_bars['close'] < extension_price).sum()
            # Also check momentum is down
            is_declining = recent_bars['close'].iloc[-1] < recent_bars['close'].iloc[0]
            return acceptance_count >= (min_bars - 1) and is_declining
        else:
            # For downside extension, need to see closes above extension low
            acceptance_count = (recent_bars['close'] > extension_price).sum()
            # Also check momentum is up
            is_rising = recent_bars['close'].iloc[-1] > recent_bars['close'].iloc[0]
            return acceptance_count >= (min_bars - 1) and is_rising
    
    def _calculate_stop(
        self,
        extension_price: float,
        direction: Direction,
        extension_range: float,
    ) -> float:
        """Calculate initial stop price.
        
        Args:
            extension_price: Extension extreme
            direction: Trade direction
            extension_range: Size of extension
            
        Returns:
            Stop price
        """
        buffer_r = self.config['stop_buffer_r']
        buffer = extension_range * buffer_r
        
        if direction == Direction.LONG:
            # For long (downside extension), stop below extension low
            return extension_price - buffer
        else:
            # For short (upside extension), stop above extension high
            return extension_price + buffer
    
    def _calculate_profit_targets(
        self,
        entry_price: float,
        stop_price: float,
        ib: Dict[str, float],
        direction: Direction,
    ) -> List[ProfitTarget]:
        """Calculate profit targets.
        
        Target 1: IB midpoint (50% position)
        Target 2: Opposite IB extreme (30% position)
        Target 3: Runner (20% position)
        
        Args:
            entry_price: Entry price
            stop_price: Stop price
            ib: Initial Balance dict
            direction: Trade direction
            
        Returns:
            List of profit targets
        """
        initial_risk = abs(entry_price - stop_price)
        
        targets = []
        
        # Target 1: IB midpoint
        t1_price = ib['midpoint']
        t1_r = abs(t1_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t1_price,
            size_pct=0.5,
            label="IB Midpoint",
            r_multiple=t1_r
        ))
        
        # Target 2: Opposite IB extreme
        if direction == Direction.LONG:
            t2_price = ib['high']
        else:
            t2_price = ib['low']
        
        t2_r = abs(t2_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t2_price,
            size_pct=0.3,
            label="IB Extreme",
            r_multiple=t2_r
        ))
        
        # Target 3: Runner (1.5x to opposite extreme)
        if direction == Direction.LONG:
            t3_price = t2_price + (ib['range'] * 0.5)
        else:
            t3_price = t2_price - (ib['range'] * 0.5)
        
        t3_r = abs(t3_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t3_price,
            size_pct=0.2,
            label="Runner",
            r_multiple=t3_r
        ))
        
        return targets
    
    def _calculate_signal_strength(
        self,
        aer: float,
        extension_range: float,
        ib: Dict[str, float],
        features: Dict[str, float],
    ) -> float:
        """Calculate signal strength (0-1).
        
        Factors:
        - Lower AER = stronger
        - Larger extension = stronger
        - Higher rotation entropy = stronger (range-bound)
        
        Args:
            aer: Auction Efficiency Ratio
            extension_range: Size of extension
            ib: Initial Balance
            features: Current market features
            
        Returns:
            Strength score (0-1)
        """
        # Component 1: AER (lower is better)
        aer_score = 1.0 - (aer / self.config['max_aer'])
        aer_score = np.clip(aer_score, 0, 1)
        
        # Component 2: Extension size (larger is better)
        extension_ratio = extension_range / ib['range']
        extension_score = min(extension_ratio / 3.0, 1.0)  # Cap at 3x
        
        # Component 3: Rotation entropy (higher = more range-bound)
        rotation_entropy = features.get('rotation_entropy', 0.5)
        entropy_score = rotation_entropy
        
        # Weighted combination
        strength = (
            0.5 * aer_score +
            0.3 * extension_score +
            0.2 * entropy_score
        )
        
        return float(np.clip(strength, 0, 1))
    
    def _has_open_position(self, open_positions: List[Any]) -> bool:
        """Check if already have open position from this playbook."""
        for pos in open_positions:
            if hasattr(pos, 'playbook_name') and pos.playbook_name == self.name:
                return True
        return False
    
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
        """Calculate price velocity (movement speed).
        
        Args:
            bars: Recent bars
            direction: Trade direction
            
        Returns:
            Velocity score
        """
        recent = bars.tail(5)
        
        if len(recent) < 2:
            return 0.5
        
        if direction == Direction.LONG:
            # For long, want upward movement
            price_change = recent['close'].iloc[-1] - recent['close'].iloc[0]
        else:
            # For short, want downward movement
            price_change = recent['close'].iloc[0] - recent['close'].iloc[-1]
        
        atr = (recent['high'] - recent['low']).mean()
        
        if atr == 0:
            return 0.5
        
        velocity = price_change / (atr * len(recent))
        
        return float(np.clip(velocity, 0, 1))

