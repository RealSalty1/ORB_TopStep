"""Opening Drive Reversal Playbook.

Fade strategy that targets weak opening drives in the first 5-15 minutes.

Key Concepts:
- Opening Drive: Aggressive move in first 5-15 minutes post-open
- Tape Speed: Trade arrival rate (declining = exhaustion)
- Volume Delta: Buy vs Sell aggression (declining = weakness)
- Block Trade Filter: Avoid fading institutional conviction
- Gap Treatment: Different handling for gap vs non-gap opens

Strategy Logic:
1. Identify opening drive (first 5-15 minutes)
2. Measure tape speed (trade arrival rate declining)
3. Calculate volume delta distribution (kurtosis, skew)
4. Filter out block trades (>2σ size)
5. Enter on exhaustion signals
6. Target: Opening price or prior close
7. Stop: Recent extreme + buffer

Based on Dr. Hoffman's specifications in 10_08_project_review.md Section 4.3
"""

from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger

from orb_confluence.strategy.playbook_base import (
    Playbook, Signal, ProfitTarget, Direction
)


class OpeningDriveReversalPlaybook(Playbook):
    """Opening Drive Reversal - Fade Weak Opening Momentum.
    
    Fades exhausted opening drives that lack conviction.
    
    Example:
        >>> playbook = OpeningDriveReversalPlaybook(
        ...     min_drive_minutes=5,
        ...     max_drive_minutes=15,
        ...     min_tape_decline=0.3,
        ... )
        >>> signal = playbook.check_entry(bars, current_bar, regime, features, [])
    """
    
    def __init__(
        self,
        min_drive_minutes: int = 5,
        max_drive_minutes: int = 15,
        min_drive_range: float = 4.0,  # Points
        min_tape_decline: float = 0.3,
        max_volume_delta_kurtosis: float = 3.0,
        block_trade_threshold_sigma: float = 2.0,
        stop_buffer_r: float = 0.25,
    ):
        """Initialize Opening Drive Reversal playbook.
        
        Args:
            min_drive_minutes: Minimum minutes for drive (default: 5)
            max_drive_minutes: Maximum minutes for drive (default: 15)
            min_drive_range: Minimum range in points (default: 4.0)
            min_tape_decline: Minimum tape speed decline (default: 0.3)
            max_volume_delta_kurtosis: Max kurtosis (higher = conviction, default: 3.0)
            block_trade_threshold_sigma: Sigma for block trade filter (default: 2.0)
            stop_buffer_r: Stop buffer as R-multiple (default: 0.25)
        """
        super().__init__()
        
        self.config = {
            'min_drive_minutes': min_drive_minutes,
            'max_drive_minutes': max_drive_minutes,
            'min_drive_range': min_drive_range,
            'min_tape_decline': min_tape_decline,
            'max_volume_delta_kurtosis': max_volume_delta_kurtosis,
            'block_trade_threshold_sigma': block_trade_threshold_sigma,
            'stop_buffer_r': stop_buffer_r,
        }
        
        # Track session open price
        self._session_open_price: Optional[float] = None
        self._prior_close_price: Optional[float] = None
    
    @property
    def name(self) -> str:
        """Playbook name."""
        return "Opening Drive Reversal"
    
    @property
    def description(self) -> str:
        """Brief description."""
        return (
            "Fades weak opening drives in first 5-15 minutes. "
            "Uses tape speed analysis and volume delta to detect exhaustion."
        )
    
    @property
    def preferred_regimes(self) -> List[str]:
        """Preferred market regimes."""
        # Works in all regimes, but strength varies
        return ["RANGE", "VOLATILE", "TRANSITIONAL", "TREND"]
    
    @property
    def playbook_type(self) -> str:
        """Playbook type."""
        return "FADE"
    
    def check_entry(
        self,
        bars: pd.DataFrame,
        current_bar: pd.Series,
        regime: str,
        features: Dict[str, float],
        open_positions: List[Any],
    ) -> Optional[Signal]:
        """Check if Opening Drive Reversal entry conditions are met.
        
        Entry Logic:
        1. Within first 15 minutes of session
        2. Identify opening drive direction and range
        3. Calculate tape speed (should be declining)
        4. Analyze volume delta distribution
        5. Filter out block trades
        6. Check gap characteristics (if gap open)
        7. Enter on exhaustion
        
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
        
        # Need to be in opening period
        if len(bars) < 5 or len(bars) > self.config['max_drive_minutes']:
            return None
        
        # Must have at least minimum drive time
        if len(bars) < self.config['min_drive_minutes']:
            return None
        
        # Set session open and prior close if not set
        if self._session_open_price is None:
            self._session_open_price = bars.iloc[0]['open']
            # Prior close would be from previous session (not in current bars)
            # For now, use first bar's open as proxy
            self._prior_close_price = bars.iloc[0]['open']
        
        # Step 1: Identify opening drive
        drive_data = self._identify_opening_drive(bars)
        if drive_data is None:
            return None
        
        direction, drive_range, drive_extreme = drive_data
        
        # Check minimum range
        if drive_range < self.config['min_drive_range']:
            return None
        
        # Step 2: Calculate tape speed
        tape_speed_data = self._calculate_tape_speed(bars)
        if tape_speed_data is None:
            return None
        
        tape_decline = tape_speed_data
        
        if tape_decline < self.config['min_tape_decline']:
            logger.debug(
                f"Opening Drive: Insufficient tape decline "
                f"({tape_decline:.2f} < {self.config['min_tape_decline']})"
            )
            return None
        
        # Step 3: Analyze volume delta
        volume_delta_data = self._analyze_volume_delta(bars, direction)
        if volume_delta_data is None:
            return None
        
        delta_kurtosis, delta_mean = volume_delta_data
        
        # High kurtosis = fat tails = block trades = institutional conviction
        if delta_kurtosis > self.config['max_volume_delta_kurtosis']:
            logger.debug(
                f"Opening Drive: High kurtosis ({delta_kurtosis:.2f}) "
                "indicates institutional conviction"
            )
            return None
        
        # Step 4: Check for block trades
        has_block_trades = self._detect_block_trades(bars)
        if has_block_trades:
            logger.debug("Opening Drive: Block trades detected, skipping fade")
            return None
        
        # Step 5: Analyze gap (if present)
        gap_size = abs(self._session_open_price - self._prior_close_price)
        is_gap = gap_size > 2.0  # 2 points
        
        if is_gap:
            gap_fill_prob = self._calculate_gap_fill_probability(
                bars, gap_size, drive_range, features
            )
            if gap_fill_prob < 0.5:
                logger.debug(f"Opening Drive: Low gap fill probability ({gap_fill_prob:.2f})")
                return None
        
        # Calculate entry, stop, targets
        entry_price = current_bar['close']
        stop_price = self._calculate_stop(drive_extreme, direction, drive_range)
        profit_targets = self._calculate_profit_targets(
            entry_price, stop_price, self._session_open_price, 
            self._prior_close_price, direction
        )
        
        # Calculate signal strength
        strength = self._calculate_signal_strength(
            tape_decline, delta_kurtosis, drive_range, is_gap, features
        )
        
        # Regime alignment is less strict for this playbook
        regime_alignment = 0.8 if regime in self.preferred_regimes else 0.6
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
                'drive_range': drive_range,
                'drive_extreme': drive_extreme,
                'tape_decline': tape_decline,
                'volume_delta_kurtosis': delta_kurtosis,
                'volume_delta_mean': delta_mean,
                'is_gap': is_gap,
                'gap_size': gap_size if is_gap else 0,
                'session_open': self._session_open_price,
                'prior_close': self._prior_close_price,
                'setup_type': 'OPENING_DRIVE_REVERSAL',
            },
            timestamp=current_bar.get('timestamp_utc'),
        )
        
        logger.info(
            f"Opening Drive {direction.value} reversal signal: "
            f"Entry={entry_price:.2f}, Drive={drive_range:.1f}pts, "
            f"Tape Decline={tape_decline:.2f}, Strength={strength:.2f}"
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
        
        Opening reversals are quick - tighter stop management.
        
        Phase 1 (0-0.4R): Keep initial stop
        Phase 2 (0.4-0.8R): Move to breakeven
        Phase 3 (>0.8R): Trail aggressively
        
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
        
        # Phase 1: Keep initial
        if mfe < 0.4:
            return current_stop
        
        # Phase 2: Breakeven
        if mfe < 0.8:
            # Breakeven + small profit
            if direction == Direction.LONG:
                new_stop = entry_price + (initial_risk * 0.05)
            else:
                new_stop = entry_price - (initial_risk * 0.05)
            
            if direction == Direction.LONG:
                return max(new_stop, current_stop)
            else:
                return min(new_stop, current_stop)
        
        # Phase 3: Aggressive trail (these are quick moves)
        trail_bars = 3
        recent = bars.tail(trail_bars)
        
        if direction == Direction.LONG:
            swing_low = recent['low'].min()
            buffer = initial_risk * 0.1
            new_stop = swing_low - buffer
            return max(new_stop, current_stop)
        else:
            swing_high = recent['high'].max()
            buffer = initial_risk * 0.1
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
        
        Opening reversals should be quick. Salvage if:
        1. Drive resumes (momentum returns)
        2. Time-based (>20 bars for opening fade)
        3. Minimal profit after reaching target zone
        
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
        # Condition 1: Drive resumes
        if mfe > 0.3:
            velocity = self._calculate_velocity(bars, position.direction)
            if velocity < -0.3:  # Strong opposite momentum
                logger.info("Opening Drive salvage: Drive resuming")
                return True
        
        # Condition 2: Time-based (quick exit expected)
        if bars_in_trade > 20:
            current_r = self._calculate_current_r(position, current_bar)
            if abs(current_r) < 0.3:
                logger.info(
                    f"Opening Drive salvage: Stalled {bars_in_trade} bars "
                    f"with only {current_r:.2f}R"
                )
                return True
        
        # Condition 3: Reached opening price but rejected
        if mfe > 0.5:
            current_r = self._calculate_current_r(position, current_bar)
            retrace_pct = (mfe - current_r) / mfe if mfe > 0 else 0
            
            if retrace_pct > 0.60:
                logger.info(f"Opening Drive salvage: Rejected (retrace={retrace_pct:.1%})")
                return True
        
        return False
    
    def _identify_opening_drive(
        self,
        bars: pd.DataFrame,
    ) -> Optional[Tuple[Direction, float, float]]:
        """Identify opening drive direction and characteristics.
        
        Args:
            bars: Opening bars
            
        Returns:
            Tuple of (direction, range, extreme_price) or None
        """
        if len(bars) < self.config['min_drive_minutes']:
            return None
        
        opening_bars = bars.copy()
        
        # Calculate net movement
        net_move = opening_bars['close'].iloc[-1] - opening_bars['open'].iloc[0]
        drive_range = opening_bars['high'].max() - opening_bars['low'].min()
        
        if drive_range == 0:
            return None
        
        # Determine direction based on net movement
        if net_move > 0:
            direction = Direction.SHORT  # Fade upward drive
            extreme = opening_bars['high'].max()
        else:
            direction = Direction.LONG  # Fade downward drive
            extreme = opening_bars['low'].min()
        
        return (direction, drive_range, extreme)
    
    def _calculate_tape_speed(
        self,
        bars: pd.DataFrame,
    ) -> Optional[float]:
        """Calculate tape speed decline.
        
        Tape speed = trade arrival rate.
        Declining speed = exhaustion.
        
        Since we have 1-minute bars, use volume as proxy for trade count.
        
        Args:
            bars: Opening bars
            
        Returns:
            Decline ratio (0-1) or None
        """
        if len(bars) < 3:
            return None
        
        # Split into first half and second half
        mid_point = len(bars) // 2
        first_half = bars.iloc[:mid_point]
        second_half = bars.iloc[mid_point:]
        
        # Calculate average "tape speed" (volume per bar as proxy)
        first_half_speed = first_half['volume'].mean()
        second_half_speed = second_half['volume'].mean()
        
        if first_half_speed == 0:
            return None
        
        # Calculate decline
        decline_ratio = (first_half_speed - second_half_speed) / first_half_speed
        
        return float(np.clip(decline_ratio, 0, 1))
    
    def _analyze_volume_delta(
        self,
        bars: pd.DataFrame,
        direction: Direction,
    ) -> Optional[Tuple[float, float]]:
        """Analyze volume delta distribution.
        
        High kurtosis = fat tails = institutional participation.
        Low kurtosis = retail = good fade candidate.
        
        Args:
            bars: Opening bars
            direction: Drive direction
            
        Returns:
            Tuple of (kurtosis, mean_delta) or None
        """
        if len(bars) < 5:
            return None
        
        bars = bars.copy()
        
        # Calculate volume delta (proxy: positive bars vs negative bars)
        # For real implementation, would use actual buy/sell volume
        bars['bar_delta'] = np.where(
            bars['close'] > bars['open'],
            bars['volume'],  # Buying
            -bars['volume']  # Selling
        )
        
        # Calculate kurtosis
        try:
            kurt = stats.kurtosis(bars['bar_delta'].values)
            mean_delta = bars['bar_delta'].mean()
        except:
            return None
        
        return (float(kurt), float(mean_delta))
    
    def _detect_block_trades(
        self,
        bars: pd.DataFrame,
    ) -> bool:
        """Detect if block trades occurred during drive.
        
        Block trades = >2σ volume bars.
        Indicates institutional conviction - don't fade.
        
        Args:
            bars: Opening bars
            
        Returns:
            True if block trades detected
        """
        if len(bars) < 3:
            return False
        
        volume_mean = bars['volume'].mean()
        volume_std = bars['volume'].std()
        
        if volume_std == 0:
            return False
        
        threshold = volume_mean + (self.config['block_trade_threshold_sigma'] * volume_std)
        
        # Check for any bars exceeding threshold
        has_blocks = (bars['volume'] > threshold).any()
        
        return bool(has_blocks)
    
    def _calculate_gap_fill_probability(
        self,
        bars: pd.DataFrame,
        gap_size: float,
        drive_range: float,
        features: Dict[str, float],
    ) -> float:
        """Calculate probability of gap fill.
        
        Factors:
        - Gap size relative to ATR
        - Drive range relative to gap
        - First 5-minute efficiency
        
        Args:
            bars: Opening bars
            gap_size: Gap size in points
            drive_range: Opening drive range
            features: Market features
            
        Returns:
            Fill probability (0-1)
        """
        # Component 1: Gap size (larger gaps less likely to fill quickly)
        # Assume ATR ~40 points for ES
        atr_proxy = 40.0
        gap_ratio = gap_size / atr_proxy
        gap_score = 1.0 - min(gap_ratio / 2.0, 1.0)  # Larger gap = lower score
        
        # Component 2: Drive exhaustion (drive much smaller than gap = likely fill)
        drive_ratio = drive_range / gap_size if gap_size > 0 else 1.0
        drive_score = 1.0 - min(drive_ratio, 1.0)  # Smaller drive = higher score
        
        # Component 3: Path efficiency (choppy = more likely to fill)
        yield_curve = features.get('intraday_yield_curve', 10.0)
        efficiency_score = min(yield_curve / 20.0, 1.0)  # Higher = choppier = more fill
        
        # Combine
        fill_prob = (
            0.4 * gap_score +
            0.4 * drive_score +
            0.2 * efficiency_score
        )
        
        return float(np.clip(fill_prob, 0, 1))
    
    def _calculate_stop(
        self,
        drive_extreme: float,
        direction: Direction,
        drive_range: float,
    ) -> float:
        """Calculate initial stop.
        
        Args:
            drive_extreme: Extreme of opening drive
            direction: Trade direction (opposite of drive)
            drive_range: Size of drive
            
        Returns:
            Stop price
        """
        buffer_r = self.config['stop_buffer_r']
        buffer = drive_range * buffer_r
        
        if direction == Direction.LONG:
            # Fading down drive, stop below recent low
            return drive_extreme - buffer
        else:
            # Fading up drive, stop above recent high
            return drive_extreme + buffer
    
    def _calculate_profit_targets(
        self,
        entry_price: float,
        stop_price: float,
        session_open: float,
        prior_close: float,
        direction: Direction,
    ) -> List[ProfitTarget]:
        """Calculate profit targets.
        
        T1: Opening price (50%)
        T2: Prior close (30%)
        T3: Runner (20%)
        
        Args:
            entry_price: Entry price
            stop_price: Stop price
            session_open: Session opening price
            prior_close: Prior session close
            direction: Trade direction
            
        Returns:
            List of profit targets
        """
        initial_risk = abs(entry_price - stop_price)
        
        targets = []
        
        # Target 1: Opening price (primary magnet)
        t1_price = session_open
        t1_r = abs(t1_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t1_price,
            size_pct=0.5,
            label="Opening Price",
            r_multiple=t1_r
        ))
        
        # Target 2: Prior close (secondary)
        t2_price = prior_close
        t2_r = abs(t2_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t2_price,
            size_pct=0.3,
            label="Prior Close",
            r_multiple=t2_r
        ))
        
        # Target 3: Runner (beyond prior close)
        if direction == Direction.LONG:
            t3_price = prior_close + (initial_risk * 0.5)
        else:
            t3_price = prior_close - (initial_risk * 0.5)
        
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
        tape_decline: float,
        delta_kurtosis: float,
        drive_range: float,
        is_gap: bool,
        features: Dict[str, float],
    ) -> float:
        """Calculate signal strength (0-1).
        
        Factors:
        - Tape decline (higher = stronger)
        - Delta kurtosis (lower = stronger for fade)
        - Drive range (moderate = best)
        - Rotation entropy (higher = choppier = better fade)
        
        Args:
            tape_decline: Tape speed decline
            delta_kurtosis: Volume delta kurtosis
            drive_range: Opening drive range
            is_gap: Whether gap open
            features: Market features
            
        Returns:
            Strength score (0-1)
        """
        # Component 1: Tape decline
        tape_score = tape_decline
        
        # Component 2: Kurtosis (lower = weaker hands = better fade)
        kurt_score = 1.0 - min(delta_kurtosis / 5.0, 1.0)
        
        # Component 3: Drive range (moderate is best, 4-10 points ideal)
        if drive_range < 4.0:
            range_score = drive_range / 4.0
        elif drive_range > 10.0:
            range_score = max(1.0 - ((drive_range - 10.0) / 10.0), 0.3)
        else:
            range_score = 1.0
        
        # Component 4: Rotation entropy (higher = choppier = better fade)
        rotation = features.get('rotation_entropy', 0.5)
        rotation_score = rotation
        
        # Weighted combination
        strength = (
            0.35 * tape_score +
            0.25 * kurt_score +
            0.20 * range_score +
            0.20 * rotation_score
        )
        
        # Penalty for gap opens (riskier)
        if is_gap:
            strength *= 0.85
        
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
        """Calculate price velocity."""
        recent = bars.tail(5)
        
        if len(recent) < 3:
            return 0.0
        
        # Simple momentum
        price_change = recent['close'].iloc[-1] - recent['close'].iloc[0]
        atr = (recent['high'] - recent['low']).mean()
        
        if atr == 0:
            return 0.0
        
        velocity = price_change / (atr * len(recent))
        
        # For wanted direction
        if direction == Direction.LONG:
            return float(np.clip(velocity, -1, 1))
        else:
            return float(np.clip(-velocity, -1, 1))

