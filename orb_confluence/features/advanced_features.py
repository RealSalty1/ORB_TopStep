"""Advanced feature engineering for regime detection and playbook optimization.

Implements 8 institutional-grade features as specified in the 10_08_project_review:
1. Volatility Term Structure - Cross-timeframe energy transfer
2. Overnight Auction Imbalance - Inventory asymmetry
3. Rotation Entropy - Price path complexity
4. Relative Volume Intensity - Participation conviction
5. Directional Commitment - Initiative vs responsive behavior
6. Microstructure Pressure - Order flow imbalance
7. Intraday Yield Curve - Path efficiency
8. Composite Liquidity Score - Market depth quality
"""

from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
from loguru import logger


class AdvancedFeatures:
    """Institutional-grade feature engineering for multi-playbook strategy.
    
    All features are designed to be:
    - Fast to calculate (<10ms per feature)
    - Robust to missing data
    - Statistically meaningful
    - Non-redundant with each other
    
    Example:
        >>> features = AdvancedFeatures()
        >>> bars_1m = loader.load("ES", start_date="2025-01-01")
        >>> bars_daily = loader.load("ES", start_date="2024-01-01")
        >>> vts = features.volatility_term_structure(bars_1m, bars_daily)
        >>> print(f"Volatility Term Structure: {vts:.3f}")
    """
    
    def __init__(self):
        """Initialize feature calculator."""
        self.cache: Dict[str, Any] = {}
    
    def volatility_term_structure(
        self,
        bars_1m: pd.DataFrame,
        bars_daily: pd.DataFrame,
        atr_period_1m: int = 14,
        atr_period_daily: int = 20,
    ) -> float:
        """Calculate volatility term structure.
        
        Formula: ATR(14, 1m) / ATR(20, daily)
        
        Interpretation:
        - > 1.0: Intraday volatility elevated vs. daily (high energy, potential breakout)
        - ~ 1.0: Normal volatility regime
        - < 1.0: Intraday volatility compressed (potential coiling)
        
        Args:
            bars_1m: 1-minute bars (recent, e.g., last 24 hours)
            bars_daily: Daily bars (at least 30 days for context)
            atr_period_1m: ATR period for 1-minute bars
            atr_period_daily: ATR period for daily bars
            
        Returns:
            Volatility term structure ratio
        """
        # Return neutral value if no daily bars
        if bars_daily is None or len(bars_daily) < 20:
            return 0.5
        
        # Calculate intraday ATR (1-minute)
        bars_1m = bars_1m.copy()
        bars_1m['tr'] = self._calculate_true_range(bars_1m)
        atr_1m = bars_1m['tr'].rolling(atr_period_1m).mean().iloc[-1]
        
        # Calculate daily ATR
        bars_daily = bars_daily.copy()
        bars_daily['tr'] = self._calculate_true_range(bars_daily)
        atr_daily = bars_daily['tr'].rolling(atr_period_daily).mean().iloc[-1]
        
        if atr_daily == 0 or np.isnan(atr_daily):
            logger.warning("Daily ATR is zero or NaN, returning neutral value 1.0")
            return 1.0
        
        vts = atr_1m / atr_daily
        
        logger.debug(f"VTS: ATR_1m={atr_1m:.2f}, ATR_daily={atr_daily:.2f}, ratio={vts:.3f}")
        
        return float(vts)
    
    def overnight_auction_imbalance(
        self,
        overnight_bars: pd.DataFrame,
        min_bars: int = 10,
    ) -> float:
        """Calculate overnight auction imbalance.
        
        Formula: |ON_POC - ON_VWAP| / ON_Range
        
        Interpretation:
        - High (>0.3): Imbalanced overnight auction, potential reversion
        - Low (<0.15): Balanced overnight auction, well-distributed
        
        Args:
            overnight_bars: Bars from prior close to current open
            min_bars: Minimum bars required for valid calculation
            
        Returns:
            Overnight imbalance ratio (0-1)
        """
        if len(overnight_bars) < min_bars:
            logger.warning(f"Insufficient overnight bars: {len(overnight_bars)} < {min_bars}")
            return 0.0
        
        # Calculate VWAP
        overnight_bars = overnight_bars.copy()
        overnight_bars['typical_price'] = (
            overnight_bars['high'] + overnight_bars['low'] + overnight_bars['close']
        ) / 3
        overnight_bars['pv'] = overnight_bars['typical_price'] * overnight_bars['volume']
        
        vwap = overnight_bars['pv'].sum() / overnight_bars['volume'].sum()
        
        # Calculate POC (Point of Control) - price with most volume
        # Use price buckets for discrete POC
        price_bins = pd.cut(overnight_bars['typical_price'], bins=50)
        volume_by_price = overnight_bars.groupby(price_bins)['volume'].sum()
        poc_bin = volume_by_price.idxmax()
        poc = (poc_bin.left + poc_bin.right) / 2  # Midpoint of bin
        
        # Calculate range
        on_range = overnight_bars['high'].max() - overnight_bars['low'].min()
        
        if on_range == 0:
            logger.warning("Overnight range is zero")
            return 0.0
        
        imbalance = abs(poc - vwap) / on_range
        
        logger.debug(f"ON Imbalance: POC={poc:.2f}, VWAP={vwap:.2f}, range={on_range:.2f}, imbalance={imbalance:.3f}")
        
        return float(np.clip(imbalance, 0, 1))
    
    def rotation_entropy(
        self,
        bars: pd.DataFrame,
        lookback_bars: int = 60,
    ) -> float:
        """Calculate rotation entropy (price path complexity).
        
        Formula: -Σ pᵢ log(pᵢ) where pᵢ = rotation_bars / total_bars
        
        Rotation bar = bar where high > prev high and low < prev low
        
        Interpretation:
        - High (>0.6): Complex, choppy price action (range-bound)
        - Low (<0.3): Directional, clean trending moves
        
        Args:
            bars: Recent bars for analysis
            lookback_bars: Number of bars to analyze
            
        Returns:
            Entropy value (0-1, normalized)
        """
        if len(bars) < lookback_bars:
            lookback_bars = len(bars)
        
        bars_subset = bars.tail(lookback_bars).copy()
        
        # Identify rotation bars
        bars_subset['rotation'] = (
            (bars_subset['high'] > bars_subset['high'].shift(1)) &
            (bars_subset['low'] < bars_subset['low'].shift(1))
        ).astype(int)
        
        # Calculate proportions
        n_rotation = bars_subset['rotation'].sum()
        n_directional = lookback_bars - n_rotation
        
        # Avoid log(0)
        p_rotation = (n_rotation + 1) / (lookback_bars + 2)
        p_directional = (n_directional + 1) / (lookback_bars + 2)
        
        # Shannon entropy
        entropy = -(p_rotation * np.log2(p_rotation) + p_directional * np.log2(p_directional))
        
        # Normalize to 0-1 (max entropy for 2 categories is 1.0)
        entropy_normalized = entropy / 1.0
        
        logger.debug(f"Rotation Entropy: rotation_bars={n_rotation}/{lookback_bars}, entropy={entropy_normalized:.3f}")
        
        return float(entropy_normalized)
    
    def relative_volume_intensity(
        self,
        bars_today: pd.DataFrame,
        historical_bars: pd.DataFrame,
        first_hour_bars: int = 60,
        lookback_days: int = 20,
    ) -> float:
        """Calculate relative volume intensity.
        
        Formula: (Vol_first_hour / 20d_avg_first_hour)² - 1
        
        Interpretation:
        - > 0.5: Significantly elevated participation (conviction)
        - ~ 0.0: Normal volume
        - < -0.5: Light volume (lack of conviction)
        
        Args:
            bars_today: Today's bars (1-minute)
            historical_bars: Historical bars for baseline (at least 20 days)
            first_hour_bars: Number of bars in first hour (60 for 1-min)
            lookback_days: Days to use for historical average
            
        Returns:
            Relative volume intensity
        """
        # Current first hour volume
        if len(bars_today) < first_hour_bars:
            logger.warning(f"Insufficient bars today: {len(bars_today)} < {first_hour_bars}")
            return 0.0
        
        vol_first_hour = bars_today.head(first_hour_bars)['volume'].sum()
        
        # Return neutral value if no historical bars
        if historical_bars is None or len(historical_bars) < lookback_days * 60:
            return 0.5
        
        # Historical first hour average
        # Group by date and take first N bars of each day
        historical_bars = historical_bars.copy()
        historical_bars['date'] = historical_bars['timestamp_utc'].dt.date
        
        daily_first_hour_volumes = []
        for date, group in historical_bars.groupby('date'):
            if len(group) >= first_hour_bars:
                fh_vol = group.head(first_hour_bars)['volume'].sum()
                daily_first_hour_volumes.append(fh_vol)
        
        if len(daily_first_hour_volumes) < 5:
            logger.warning("Insufficient historical days for volume baseline")
            return 0.0
        
        avg_first_hour = np.mean(daily_first_hour_volumes[-lookback_days:])
        
        if avg_first_hour == 0:
            logger.warning("Historical average volume is zero")
            return 0.0
        
        ratio = vol_first_hour / avg_first_hour
        intensity = ratio ** 2 - 1
        
        logger.debug(f"Vol Intensity: current={vol_first_hour}, avg={avg_first_hour:.0f}, ratio={ratio:.2f}, intensity={intensity:.3f}")
        
        return float(intensity)
    
    def directional_commitment(
        self,
        bars: pd.DataFrame,
        lookback_bars: int = 60,
    ) -> float:
        """Calculate directional commitment.
        
        Formula: |Σ(close - open)| / Σ|close - open|
        
        Interpretation:
        - High (>0.7): Strong directional commitment (initiative)
        - Low (<0.3): Responsive, back-and-forth (range-bound)
        
        Args:
            bars: Recent bars for analysis
            lookback_bars: Number of bars to analyze (e.g., first hour = 60)
            
        Returns:
            Directional commitment ratio (0-1)
        """
        if len(bars) < lookback_bars:
            lookback_bars = len(bars)
        
        bars_subset = bars.tail(lookback_bars).copy()
        
        # Calculate bar bodies
        bars_subset['body'] = bars_subset['close'] - bars_subset['open']
        
        # Net directional movement
        net_movement = abs(bars_subset['body'].sum())
        
        # Total movement (absolute)
        total_movement = bars_subset['body'].abs().sum()
        
        if total_movement == 0:
            logger.warning("Total movement is zero")
            return 0.5  # Neutral
        
        commitment = net_movement / total_movement
        
        logger.debug(f"Directional Commitment: net={net_movement:.2f}, total={total_movement:.2f}, ratio={commitment:.3f}")
        
        return float(commitment)
    
    def microstructure_pressure(
        self,
        trades_1s: pd.DataFrame,
        lookback_seconds: int = 300,
    ) -> float:
        """Calculate microstructure pressure (order flow imbalance).
        
        Formula: (Bid_volume - Ask_volume) / (Bid_volume + Ask_volume)
        
        Requires 1-second bars with side information or trade-level data.
        
        Interpretation:
        - > 0.2: Buying pressure (aggressive buyers)
        - ~ 0.0: Balanced
        - < -0.2: Selling pressure (aggressive sellers)
        
        Args:
            trades_1s: 1-second bars or tick data with side information
            lookback_seconds: Seconds to analyze
            
        Returns:
            Order flow imbalance (-1 to 1)
        """
        if len(trades_1s) < lookback_seconds:
            lookback_seconds = len(trades_1s)
        
        if lookback_seconds == 0:
            return 0.0
        
        trades_subset = trades_1s.tail(lookback_seconds).copy()
        
        # If we have side information (from tick data)
        if 'side' in trades_subset.columns:
            buy_volume = trades_subset[trades_subset['side'] == 'B']['volume'].sum()
            sell_volume = trades_subset[trades_subset['side'] == 'A']['volume'].sum()
        else:
            # Approximate from price movement within bar
            # Buying pressure: close > open
            # Selling pressure: close < open
            trades_subset['buy_vol'] = np.where(
                trades_subset['close'] > trades_subset['open'],
                trades_subset['volume'],
                0
            )
            trades_subset['sell_vol'] = np.where(
                trades_subset['close'] < trades_subset['open'],
                trades_subset['volume'],
                0
            )
            buy_volume = trades_subset['buy_vol'].sum()
            sell_volume = trades_subset['sell_vol'].sum()
        
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            logger.warning("Total volume is zero for microstructure pressure")
            return 0.0
        
        pressure = (buy_volume - sell_volume) / total_volume
        
        logger.debug(f"Microstructure Pressure: buy={buy_volume}, sell={sell_volume}, pressure={pressure:.3f}")
        
        return float(np.clip(pressure, -1, 1))
    
    def intraday_yield_curve(
        self,
        bars: pd.DataFrame,
        first_hour_bars: int = 60,
    ) -> float:
        """Calculate intraday yield curve (path efficiency).
        
        Formula: Σ(high - low) / range_first_hour
        
        Interpretation:
        - High (>15): Inefficient, choppy path (range-bound)
        - Low (<8): Efficient, directional path (trending)
        
        Args:
            bars: Recent bars (should include at least first hour)
            first_hour_bars: Number of bars in first hour
            
        Returns:
            Path efficiency ratio
        """
        if len(bars) < first_hour_bars:
            logger.warning(f"Insufficient bars: {len(bars)} < {first_hour_bars}")
            return 10.0  # Neutral value
        
        first_hour = bars.head(first_hour_bars).copy()
        
        # Sum of all bar ranges
        first_hour['bar_range'] = first_hour['high'] - first_hour['low']
        total_bar_ranges = first_hour['bar_range'].sum()
        
        # Overall range of first hour
        first_hour_range = first_hour['high'].max() - first_hour['low'].min()
        
        if first_hour_range == 0:
            logger.warning("First hour range is zero")
            return 10.0
        
        yield_curve = total_bar_ranges / first_hour_range
        
        logger.debug(f"Intraday Yield Curve: bar_ranges={total_bar_ranges:.2f}, range={first_hour_range:.2f}, ratio={yield_curve:.2f}")
        
        return float(yield_curve)
    
    def composite_liquidity_score(
        self,
        bars_1s: pd.DataFrame,
        lookback_seconds: int = 300,
    ) -> float:
        """Calculate composite liquidity score.
        
        Formula: f(spread_proxy, volume, trade_size_distribution)
        
        Uses 1-second bars to estimate:
        - Spread (from bar ranges)
        - Volume consistency
        - Trade size distribution
        
        Interpretation:
        - High (>0.7): High liquidity, tight spreads, consistent volume
        - Low (<0.3): Poor liquidity, wide spreads, erratic volume
        
        Args:
            bars_1s: 1-second bars for micro-analysis
            lookback_seconds: Seconds to analyze
            
        Returns:
            Liquidity score (0-1)
        """
        if len(bars_1s) < lookback_seconds:
            lookback_seconds = len(bars_1s)
        
        if lookback_seconds < 60:
            logger.warning("Insufficient data for liquidity score")
            return 0.5  # Neutral
        
        bars_subset = bars_1s.tail(lookback_seconds).copy()
        
        # Component 1: Spread proxy (inverse of bar range / price)
        bars_subset['range'] = bars_subset['high'] - bars_subset['low']
        bars_subset['mid_price'] = (bars_subset['high'] + bars_subset['low']) / 2
        bars_subset['spread_proxy'] = bars_subset['range'] / bars_subset['mid_price']
        
        avg_spread = bars_subset['spread_proxy'].mean()
        # Lower spread = better liquidity, invert and normalize
        spread_score = 1 / (1 + avg_spread * 1000)  # Scale factor for ES
        
        # Component 2: Volume consistency (inverse of coefficient of variation)
        volume_cv = bars_subset['volume'].std() / (bars_subset['volume'].mean() + 1)
        volume_score = 1 / (1 + volume_cv)
        
        # Component 3: Active seconds (seconds with >0 volume)
        active_seconds = (bars_subset['volume'] > 0).sum()
        activity_score = active_seconds / lookback_seconds
        
        # Composite score (weighted average)
        liquidity_score = (
            0.4 * spread_score +
            0.3 * volume_score +
            0.3 * activity_score
        )
        
        logger.debug(
            f"Liquidity Score: spread={spread_score:.3f}, volume={volume_score:.3f}, "
            f"activity={activity_score:.3f}, composite={liquidity_score:.3f}"
        )
        
        return float(np.clip(liquidity_score, 0, 1))
    
    def calculate_all_features(
        self,
        bars_1m: pd.DataFrame,
        bars_daily: pd.DataFrame,
        bars_1s: Optional[pd.DataFrame] = None,
        overnight_bars: Optional[pd.DataFrame] = None,
    ) -> Dict[str, float]:
        """Calculate all 8 features at once.
        
        Args:
            bars_1m: 1-minute bars (recent session)
            bars_daily: Daily bars (for historical context)
            bars_1s: Optional 1-second bars (for microstructure features)
            overnight_bars: Optional overnight bars (for auction imbalance)
            
        Returns:
            Dictionary with all feature values
        """
        features = {}
        
        # Feature 1: Volatility Term Structure
        features['volatility_term_structure'] = self.volatility_term_structure(
            bars_1m, bars_daily
        )
        
        # Feature 2: Overnight Auction Imbalance
        if overnight_bars is not None and len(overnight_bars) > 0:
            features['overnight_auction_imbalance'] = self.overnight_auction_imbalance(
                overnight_bars
            )
        else:
            features['overnight_auction_imbalance'] = 0.0
        
        # Feature 3: Rotation Entropy
        features['rotation_entropy'] = self.rotation_entropy(bars_1m)
        
        # Feature 4: Relative Volume Intensity
        features['relative_volume_intensity'] = self.relative_volume_intensity(
            bars_1m, bars_daily
        )
        
        # Feature 5: Directional Commitment
        features['directional_commitment'] = self.directional_commitment(bars_1m)
        
        # Feature 6: Microstructure Pressure (needs 1s data)
        if bars_1s is not None and len(bars_1s) > 0:
            features['microstructure_pressure'] = self.microstructure_pressure(bars_1s)
        else:
            # Approximate from 1m bars
            features['microstructure_pressure'] = self.microstructure_pressure(bars_1m)
        
        # Feature 7: Intraday Yield Curve
        features['intraday_yield_curve'] = self.intraday_yield_curve(bars_1m)
        
        # Feature 8: Composite Liquidity Score (needs 1s data)
        if bars_1s is not None and len(bars_1s) > 0:
            features['composite_liquidity_score'] = self.composite_liquidity_score(bars_1s)
        else:
            # Approximate from 1m bars
            features['composite_liquidity_score'] = self.composite_liquidity_score(bars_1m)
        
        logger.info(f"Calculated {len(features)} features")
        
        return features
    
    @staticmethod
    def _calculate_true_range(bars: pd.DataFrame) -> pd.Series:
        """Calculate True Range for ATR calculation.
        
        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        """
        high_low = bars['high'] - bars['low']
        high_prev_close = abs(bars['high'] - bars['close'].shift(1))
        low_prev_close = abs(bars['low'] - bars['close'].shift(1))
        
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        
        return tr
    
    def clear_cache(self):
        """Clear feature cache."""
        self.cache = {}

