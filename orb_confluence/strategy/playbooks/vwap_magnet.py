"""VWAP Magnet Playbook.

Mean reversion strategy that fades extensions away from VWAP.

Key Concepts:
- VWAP: Volume-Weighted Average Price (intraday)
- Dynamic Bands: Volatility-adjusted envelopes around VWAP
- Rejection Velocity: Speed of price return to VWAP
- Multi-timeframe VWAP: Intraday, 3-day, 5-day confluence

Strategy Logic:
1. Calculate intraday VWAP
2. Monitor for extensions beyond dynamic bands
3. Measure rejection velocity (acceleration back to VWAP)
4. Enter on strong rejection with high velocity
5. Target: VWAP or opposite band
6. Stop: Beyond recent extreme

Based on Dr. Hoffman's specifications in 10_08_project_review.md Section 4.4
"""

from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from loguru import logger

from orb_confluence.strategy.playbook_base import (
    Playbook, Signal, ProfitTarget, Direction
)


class VWAPMagnetPlaybook(Playbook):
    """VWAP Magnet - Mean Reversion Playbook.
    
    Fades extensions away from VWAP with dynamic volatility bands.
    
    Example:
        >>> playbook = VWAPMagnetPlaybook(
        ...     band_multiplier=2.0,
        ...     min_rejection_velocity=0.3,
        ... )
        >>> signal = playbook.check_entry(bars, current_bar, regime, features, [])
    """
    
    def __init__(
        self,
        band_multiplier: float = 2.0,
        min_rejection_velocity: float = 0.3,
        min_bars_for_vwap: int = 30,
        time_decay_alpha: float = 0.5,
        stop_buffer_r: float = 0.2,
    ):
        """Initialize VWAP Magnet playbook.
        
        Args:
            band_multiplier: Standard deviations for VWAP bands (default: 2.0)
            min_rejection_velocity: Minimum velocity for entry (default: 0.3)
            min_bars_for_vwap: Minimum bars to calculate VWAP (default: 30)
            time_decay_alpha: Time decay factor for VWAP bands (default: 0.5)
            stop_buffer_r: Additional buffer for stops (default: 0.2)
        """
        super().__init__()
        
        self.config = {
            'band_multiplier': band_multiplier,
            'min_rejection_velocity': min_rejection_velocity,
            'min_bars_for_vwap': min_bars_for_vwap,
            'time_decay_alpha': time_decay_alpha,
            'stop_buffer_r': stop_buffer_r,
        }
    
    @property
    def name(self) -> str:
        """Playbook name."""
        return "VWAP Magnet"
    
    @property
    def description(self) -> str:
        """Brief description."""
        return (
            "Mean reversion to VWAP with dynamic volatility bands. "
            "Enters on high velocity rejection from extended levels."
        )
    
    @property
    def preferred_regimes(self) -> List[str]:
        """Preferred market regimes."""
        return ["RANGE", "TRANSITIONAL"]
    
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
    ) -> Optional[Signal]:
        """Check if VWAP Magnet entry conditions are met.
        
        Entry Logic:
        1. VWAP calculated (sufficient bars)
        2. Price extended beyond dynamic band
        3. High rejection velocity detected
        4. Not in chop (check rotation entropy)
        5. Regime alignment
        
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
        
        # Need sufficient bars
        if len(bars) < self.config['min_bars_for_vwap']:
            return None
        
        # Calculate VWAP and bands
        vwap_data = self._calculate_vwap_bands(bars)
        if vwap_data is None:
            return None
        
        vwap = vwap_data['vwap']
        upper_band = vwap_data['upper_band']
        lower_band = vwap_data['lower_band']
        vwap_std = vwap_data['std']
        
        # Check for extension beyond bands
        current_price = current_bar['close']
        
        is_above_upper = current_price > upper_band
        is_below_lower = current_price < lower_band
        
        if not (is_above_upper or is_below_lower):
            return None
        
        # Determine direction
        if is_above_upper:
            direction = Direction.SHORT  # Fade the upside extension
            extension_distance = current_price - vwap
        else:
            direction = Direction.LONG  # Fade the downside extension
            extension_distance = vwap - current_price
        
        # Calculate rejection velocity
        rejection_velocity = self._calculate_rejection_velocity(
            bars, vwap, direction
        )
        
        if rejection_velocity < self.config['min_rejection_velocity']:
            logger.debug(
                f"VWAP Magnet: Insufficient rejection velocity "
                f"({rejection_velocity:.3f} < {self.config['min_rejection_velocity']})"
            )
            return None
        
        # Check rotation entropy (avoid excessive chop)
        rotation_entropy = features.get('rotation_entropy', 0.5)
        if rotation_entropy > 0.70:
            logger.debug(f"VWAP Magnet: Excessive chop (entropy={rotation_entropy:.2f})")
            return None
        
        # Check regime alignment
        regime_alignment = self.get_regime_alignment(regime)
        if regime_alignment < 0.5:
            logger.debug(f"VWAP Magnet: Poor regime alignment ({regime})")
            return None
        
        # Calculate entry, stop, targets
        entry_price = current_price
        stop_price = self._calculate_stop(
            current_price, direction, vwap_std, extension_distance
        )
        profit_targets = self._calculate_profit_targets(
            entry_price, stop_price, vwap, upper_band, lower_band, direction
        )
        
        # Calculate signal strength
        strength = self._calculate_signal_strength(
            extension_distance, vwap_std, rejection_velocity, features
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
                'vwap': vwap,
                'upper_band': upper_band,
                'lower_band': lower_band,
                'vwap_std': vwap_std,
                'extension_distance': extension_distance,
                'rejection_velocity': rejection_velocity,
                'setup_type': 'VWAP_MAGNET',
            },
            timestamp=current_bar.get('timestamp_utc'),
        )
        
        logger.info(
            f"VWAP Magnet {direction.value} signal: "
            f"Entry={entry_price:.2f}, VWAP={vwap:.2f}, "
            f"Velocity={rejection_velocity:.2f}, Strength={strength:.2f}"
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
        
        Phase 1 (0-0.5R): Keep initial stop
        Phase 2 (0.5-1.0R): Move to breakeven
        Phase 3 (>1.0R): Trail aggressively with VWAP
        
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
        
        # Phase 1: No adjustment
        if mfe < 0.5:
            return current_stop
        
        # Phase 2: Breakeven
        if mfe < 1.0:
            if direction == Direction.LONG:
                new_stop = entry_price + (initial_risk * 0.05)
            else:
                new_stop = entry_price - (initial_risk * 0.05)
            
            if direction == Direction.LONG:
                return max(new_stop, current_stop)
            else:
                return min(new_stop, current_stop)
        
        # Phase 3: Trail with VWAP
        # Use VWAP as trailing stop once we're past it
        vwap_data = self._calculate_vwap_bands(bars)
        if vwap_data:
            vwap = vwap_data['vwap']
            buffer = initial_risk * 0.1
            
            if direction == Direction.LONG:
                new_stop = vwap - buffer
                return max(new_stop, current_stop)
            else:
                new_stop = vwap + buffer
                return min(new_stop, current_stop)
        
        # Fallback: keep current stop
        return current_stop
    
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
        1. Reached VWAP but rejected (opposite direction momentum)
        2. Time-based: >30 bars with minimal profit
        3. Deep retracement after profit
        
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
        # Condition 1: VWAP rejection
        vwap_data = self._calculate_vwap_bands(bars)
        if vwap_data and mfe > 0.3:
            vwap = vwap_data['vwap']
            current_price = current_bar['close']
            
            # Check if we reached VWAP and got rejected
            if position.direction == Direction.LONG:
                crossed_vwap = current_price >= vwap
                rejection = current_price < vwap * 0.999  # Slight rejection
                if crossed_vwap and rejection:
                    logger.info("VWAP Magnet salvage: Rejected at VWAP")
                    return True
            else:
                crossed_vwap = current_price <= vwap
                rejection = current_price > vwap * 1.001
                if crossed_vwap and rejection:
                    logger.info("VWAP Magnet salvage: Rejected at VWAP")
                    return True
        
        # Condition 2: Time-based stall (shorter than IB Fade)
        if bars_in_trade > 30:
            current_r = self._calculate_current_r(position, current_bar)
            if abs(current_r) < 0.2:
                logger.info(
                    f"VWAP Magnet salvage: Stalled {bars_in_trade} bars "
                    f"with only {current_r:.2f}R"
                )
                return True
        
        # Condition 3: Deep retracement
        if mfe > 0.5:
            current_r = self._calculate_current_r(position, current_bar)
            retrace_pct = (mfe - current_r) / mfe if mfe > 0 else 0
            
            if retrace_pct > 0.65:  # Slightly tighter than IB Fade
                logger.info(
                    f"VWAP Magnet salvage: Retraced {retrace_pct:.1%} from MFE"
                )
                return True
        
        return False
    
    def _calculate_vwap_bands(
        self,
        bars: pd.DataFrame,
    ) -> Optional[Dict[str, float]]:
        """Calculate VWAP with dynamic bands.
        
        Formula: VWAP_upper = VWAP + k × σ_VWAP × √(t/T)
        
        Args:
            bars: Historical bars (should be intraday session)
            
        Returns:
            Dict with vwap, upper_band, lower_band, std
        """
        if len(bars) < self.config['min_bars_for_vwap']:
            return None
        
        # Calculate typical price
        bars = bars.copy()
        bars['typical_price'] = (bars['high'] + bars['low'] + bars['close']) / 3
        
        # Calculate cumulative VWAP
        bars['pv'] = bars['typical_price'] * bars['volume']
        bars['cumulative_pv'] = bars['pv'].cumsum()
        bars['cumulative_volume'] = bars['volume'].cumsum()
        
        # Current VWAP
        vwap = bars['cumulative_pv'].iloc[-1] / bars['cumulative_volume'].iloc[-1]
        
        # Calculate VWAP standard deviation
        bars['squared_diff'] = (bars['typical_price'] - vwap) ** 2
        bars['weighted_squared_diff'] = bars['squared_diff'] * bars['volume']
        variance = bars['weighted_squared_diff'].sum() / bars['cumulative_volume'].iloc[-1]
        vwap_std = np.sqrt(variance)
        
        if vwap_std == 0:
            logger.warning("VWAP std is zero")
            return None
        
        # Time decay factor: √(t/T)
        # t = bars elapsed, T = expected total bars in session (~390 for full day)
        t = len(bars)
        T = 390
        time_decay = np.sqrt(t / T) if t < T else 1.0
        
        # Adjust time decay with alpha
        alpha = self.config['time_decay_alpha']
        time_decay = time_decay ** alpha
        
        # Calculate bands
        k = self.config['band_multiplier']
        band_width = k * vwap_std * time_decay
        
        upper_band = vwap + band_width
        lower_band = vwap - band_width
        
        return {
            'vwap': float(vwap),
            'upper_band': float(upper_band),
            'lower_band': float(lower_band),
            'std': float(vwap_std),
        }
    
    def _calculate_rejection_velocity(
        self,
        bars: pd.DataFrame,
        vwap: float,
        direction: Direction,
    ) -> float:
        """Calculate rejection velocity (speed of return to VWAP).
        
        Measures acceleration of price back toward VWAP.
        
        Args:
            bars: Historical bars
            vwap: Current VWAP
            direction: Trade direction (SHORT = rejecting from above)
            
        Returns:
            Velocity score (0-1)
        """
        lookback = 5
        recent = bars.tail(lookback)
        
        if len(recent) < 3:
            return 0.0
        
        # Calculate distance from VWAP over time
        recent = recent.copy()
        recent['distance_from_vwap'] = recent['close'] - vwap
        
        # Calculate velocity (change in distance / bars)
        start_distance = recent['distance_from_vwap'].iloc[0]
        end_distance = recent['distance_from_vwap'].iloc[-1]
        distance_change = start_distance - end_distance  # Positive = moving toward VWAP
        
        # Normalize by ATR
        atr = (recent['high'] - recent['low']).mean()
        if atr == 0:
            return 0.0
        
        velocity = distance_change / (atr * lookback)
        
        # For SHORT (rejecting from above), want positive velocity (moving down)
        # For LONG (rejecting from below), want positive velocity (moving up)
        if direction == Direction.SHORT:
            # Already correct: positive distance_change means moving down toward VWAP
            pass
        else:
            # Need to flip sign for LONG
            velocity = -velocity
        
        # Clip to 0-1
        velocity = np.clip(velocity, 0, 1)
        
        return float(velocity)
    
    def _calculate_stop(
        self,
        entry_price: float,
        direction: Direction,
        vwap_std: float,
        extension_distance: float,
    ) -> float:
        """Calculate initial stop.
        
        Stop placed beyond recent extreme with buffer.
        
        Args:
            entry_price: Entry price
            direction: Trade direction
            vwap_std: VWAP standard deviation
            extension_distance: Distance from VWAP to entry
            
        Returns:
            Stop price
        """
        # Use a fraction of the extension distance as stop
        stop_distance = extension_distance * 0.4 + vwap_std * 0.5
        
        buffer_r = self.config['stop_buffer_r']
        stop_distance = stop_distance * (1 + buffer_r)
        
        if direction == Direction.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance
    
    def _calculate_profit_targets(
        self,
        entry_price: float,
        stop_price: float,
        vwap: float,
        upper_band: float,
        lower_band: float,
        direction: Direction,
    ) -> List[ProfitTarget]:
        """Calculate profit targets.
        
        T1: VWAP (primary target) - 60%
        T2: Opposite band - 25%
        T3: Runner - 15%
        
        Args:
            entry_price: Entry price
            stop_price: Stop price
            vwap: Current VWAP
            upper_band: Upper band
            lower_band: Lower band
            direction: Trade direction
            
        Returns:
            List of profit targets
        """
        initial_risk = abs(entry_price - stop_price)
        
        targets = []
        
        # Target 1: VWAP (main magnet)
        t1_price = vwap
        t1_r = abs(t1_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t1_price,
            size_pct=0.6,
            label="VWAP",
            r_multiple=t1_r
        ))
        
        # Target 2: Opposite band
        if direction == Direction.LONG:
            t2_price = upper_band
        else:
            t2_price = lower_band
        
        t2_r = abs(t2_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t2_price,
            size_pct=0.25,
            label="Opposite Band",
            r_multiple=t2_r
        ))
        
        # Target 3: Runner (beyond opposite band)
        band_width = upper_band - lower_band
        if direction == Direction.LONG:
            t3_price = t2_price + (band_width * 0.3)
        else:
            t3_price = t2_price - (band_width * 0.3)
        
        t3_r = abs(t3_price - entry_price) / initial_risk if initial_risk > 0 else 0
        targets.append(ProfitTarget(
            price=t3_price,
            size_pct=0.15,
            label="Runner",
            r_multiple=t3_r
        ))
        
        return targets
    
    def _calculate_signal_strength(
        self,
        extension_distance: float,
        vwap_std: float,
        rejection_velocity: float,
        features: Dict[str, float],
    ) -> float:
        """Calculate signal strength (0-1).
        
        Factors:
        - Extension size (larger = stronger)
        - Rejection velocity (higher = stronger)
        - Liquidity score (higher = better)
        
        Args:
            extension_distance: Distance from VWAP
            vwap_std: VWAP standard deviation
            rejection_velocity: Rejection velocity
            features: Market features
            
        Returns:
            Strength score (0-1)
        """
        # Component 1: Extension size
        extension_score = min(extension_distance / (vwap_std * 3), 1.0)
        
        # Component 2: Rejection velocity (already 0-1)
        velocity_score = rejection_velocity
        
        # Component 3: Liquidity (higher = cleaner mean reversion)
        liquidity = features.get('composite_liquidity_score', 0.5)
        liquidity_score = liquidity
        
        # Weighted combination
        strength = (
            0.3 * extension_score +
            0.5 * velocity_score +
            0.2 * liquidity_score
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

