"""ORB 2.0 integrated backtest engine.

Combines all new components:
- Dual OR layers (micro + primary adaptive)
- Auction state classification
- Context exclusion matrix
- Playbooks (PB1, PB2, PB3)
- Two-phase stops & salvage
- Trailing modes
- Probability gating
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
from loguru import logger

from ..features import (
    DualORBuilder,
    AuctionMetricsBuilder,
    FeatureTableBuilder,
)
from ..features.auction_metrics import GapType
from ..states import (
    classify_auction_state,
    ContextExclusionMatrix,
    AuctionState,
)
from ..playbooks import (
    ORBRefinedPlaybook,
    FailureFadePlaybook,
    PullbackContinuationPlaybook,
)
from ..risk import (
    TwoPhaseStopManager,
    SalvageManager,
    TrailingStopManager,
    PartialExitManager,
    PartialTarget,
)
from ..signals import ProbabilityGate, ProbabilityGateConfig
from ..analytics.mfe_mae import MFEMAETracker


@dataclass
class ORB2Config:
    """ORB 2.0 configuration."""
    
    # OR configuration
    micro_minutes: int = 5
    primary_base_minutes: int = 15
    primary_min_minutes: int = 10
    primary_max_minutes: int = 20
    low_vol_threshold: float = 0.35
    high_vol_threshold: float = 0.85
    
    # Auction state thresholds
    drive_energy_threshold: float = 0.55
    rotations_initiative_max: int = 2
    
    # Context exclusion
    use_context_exclusion: bool = True
    min_trades_per_cell: int = 30
    
    # Playbooks
    enable_pb1: bool = True  # ORB Refined
    enable_pb2: bool = True  # Failure Fade
    enable_pb3: bool = True  # Pullback Continuation
    
    # Risk management
    use_two_phase_stops: bool = True
    use_salvage: bool = True
    phase2_trigger_r: float = 0.6
    salvage_trigger_mfe_r: float = 0.4
    salvage_retrace_threshold: float = 0.65
    
    # ✨ PHASE 1 OPTIMIZATIONS
    stop_multiplier: float = 1.3  # Widen stops by 30% to reduce noise stop-outs
    breakeven_trigger_r: float = 0.2  # ✨ PHASE 1.1: Tightened from 0.3R to 0.2R
    use_partial_exits: bool = True  # Enable partial profit taking
    
    # ✨ PHASE 1.1: Adjusted partial levels - Let MORE run to target!
    partial_target_1_r: float = 0.75  # First partial at +0.75R (was 0.5R)
    partial_target_1_size: float = 0.25  # Exit 25% at first target (was 50%)
    partial_target_2_r: float = 1.25  # Second partial at +1.25R (was 1.0R)
    partial_target_2_size: float = 0.25  # Exit 25% at second target
    # Remaining 50% runs to full +1.5R target (was only 25%)
    
    # Probability gating
    use_probability_gating: bool = False  # Start without model
    p_min_floor: float = 0.35
    p_runner_threshold: float = 0.55
    
    # ✨ Time filters (Phase 1 optimization)
    use_time_filters: bool = True
    avoid_first_minutes_after_or: int = 15  # Minutes after OR close to avoid
    lunch_start_hour: int = 11  # CT (12:30 ET = 11:30 CT)
    lunch_start_minute: int = 30
    lunch_end_hour: int = 13  # CT (14:00 ET = 13:00 CT)
    lunch_end_minute: int = 0
    
    # 🎯 PHASE 2: CONSISTENCY ENHANCEMENTS
    use_daily_loss_limit: bool = True  # Stop trading if daily loss limit hit
    daily_loss_limit_r: float = -2.0  # Max loss per day in R
    
    use_regime_filter: bool = False  # DISABLED: ADX too strict for intraday
    adx_period: int = 14
    adx_trending_threshold: float = 15.0  # ADX > 15 = trending (relaxed)
    
    use_or_width_filter: bool = False  # DISABLED: Too strict, filters too many days
    
    use_intraday_monitor: bool = True  # Shut down if bleeding intraday
    intraday_stop_loss_r: float = -1.5  # Stop new trades if down >1.5R by noon
    intraday_check_hour: int = 12  # CT time to check
    
    # 🚀 PHASE 2B: ENTRY QUALITY FILTERS
    use_momentum_filter: bool = True  # Require price momentum on breakout
    min_breakout_velocity: float = 0.3  # Min % move per minute (in ATR units)
    
    use_volume_confirmation: bool = True  # Require volume spike
    min_volume_ratio: float = 1.5  # Volume must be >1.5x recent average
    
    use_trend_alignment: bool = True  # Trade with broader trend only
    fast_ema_period: int = 5  # Fast EMA for trend (5 bars)
    slow_ema_period: int = 15  # Slow EMA for trend (15 bars)
    
    use_price_action_filter: bool = True  # Clean breakouts only
    max_wick_ratio: float = 0.4  # Max wick size (40% of candle)
    
    use_reentry_cooldown: bool = True  # Prevent overtrading
    reentry_cooldown_minutes: int = 5  # Minutes between trades same direction
    
    # General
    atr_period: int = 14
    adr_period: int = 20


@dataclass
class ORB2Trade:
    """Enhanced trade record with ORB 2.0 metadata."""
    
    trade_id: str
    playbook_name: str
    direction: str
    
    # Entry/Exit
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Performance
    realized_r: Optional[float] = None
    mfe_r: float = 0.0
    mae_r: float = 0.0
    
    # Context
    auction_state: str = "UNKNOWN"
    or_width_norm: float = 0.0
    context_excluded: bool = False
    p_extension: Optional[float] = None
    
    # Stops
    initial_stop: float = 0.0
    final_stop: float = 0.0
    stop_phase: str = "PHASE1"
    salvage_triggered: bool = False


class ORB2Engine:
    """ORB 2.0 integrated backtest engine.
    
    Example:
        >>> config = ORB2Config()
        >>> engine = ORB2Engine(config)
        >>> 
        >>> # Optional: fit exclusion matrix on historical data
        >>> engine.fit_exclusion_matrix(historical_trades_df)
        >>> 
        >>> # Run backtest
        >>> results = engine.run(bars_df, instrument="ES")
    """
    
    def __init__(self, config: ORB2Config):
        """Initialize ORB 2.0 engine.
        
        Args:
            config: ORB 2.0 configuration
        """
        self.config = config
        
        # Components (initialized per session)
        self.or_builder: Optional[DualORBuilder] = None
        self.auction_builder: Optional[AuctionMetricsBuilder] = None
        self.feature_builder: Optional[FeatureTableBuilder] = None
        
        # Playbooks
        self.playbooks = []
        if config.enable_pb1:
            self.playbooks.append(ORBRefinedPlaybook())
        if config.enable_pb2:
            self.playbooks.append(FailureFadePlaybook())
        if config.enable_pb3:
            self.playbooks.append(PullbackContinuationPlaybook())
        
        # Context exclusion
        self.exclusion_matrix: Optional[ContextExclusionMatrix] = None
        if config.use_context_exclusion:
            self.exclusion_matrix = ContextExclusionMatrix(
                min_trades_per_cell=config.min_trades_per_cell
            )
        
        # Probability gate
        if config.use_probability_gating:
            gate_config = ProbabilityGateConfig(
                p_min_floor=config.p_min_floor,
                p_runner_threshold=config.p_runner_threshold,
            )
            self.prob_gate = ProbabilityGate(gate_config)
        else:
            self.prob_gate = None
        
        # Active trade tracking
        self.active_trades: Dict[str, dict] = {}  # trade_id -> trade state
        
        # Results
        self.completed_trades: List[ORB2Trade] = []
        self.cumulative_r = 0.0
        
        # 🎯 PHASE 2: Daily P&L tracking for loss limit
        self.daily_r = 0.0  # Reset per session
        self.daily_shutdown = False  # Flag to stop new trades
        
        # 🚀 PHASE 2B: Entry quality tracking
        self.last_trade_time = {"long": None, "short": None}  # Track last entry per direction
        
        logger.info(f"ORB 2.0 Engine initialized with {len(self.playbooks)} playbooks")
    
    def fit_exclusion_matrix(self, trades_df: pd.DataFrame) -> None:
        """Fit context exclusion matrix on historical data.
        
        Args:
            trades_df: DataFrame with historical trades
        """
        if self.exclusion_matrix is None:
            logger.warning("Context exclusion disabled, skipping fit")
            return
        
        logger.info("Fitting context exclusion matrix...")
        self.exclusion_matrix.fit(
            trades_df,
            or_width_norm_col="or_width_norm",
            breakout_delay_col="breakout_delay_minutes",
            volume_quality_col="volume_quality_score",
            auction_state_col="auction_state",
            gap_type_col="gap_type",
            realized_r_col="realized_r",
        )
        
        logger.info(f"Exclusion matrix fitted: {len(self.exclusion_matrix.cells)} cells")
    
    def run(
        self,
        bars: pd.DataFrame,
        instrument: str = "ES",
        session_date: str = None,
    ) -> Dict:
        """Run backtest on bar data.
        
        Args:
            bars: DataFrame with OHLCV data and timestamp_utc
            instrument: Instrument name
            session_date: Session date (YYYY-MM-DD)
            
        Returns:
            Dictionary with results
        """
        if session_date is None:
            session_date = bars.iloc[0]["timestamp_utc"].strftime("%Y-%m-%d")
        
        logger.info(f"Running ORB 2.0 backtest: {instrument} {session_date}, {len(bars)} bars")
        
        # 🎯 PHASE 2: Reset daily tracking
        self.daily_r = 0.0
        self.daily_shutdown = False
        
        # 🚀 PHASE 2B: Reset entry quality tracking
        self.last_trade_time = {"long": None, "short": None}
        
        # Initialize session
        self._initialize_session(bars.iloc[0]["timestamp_utc"], instrument, session_date)
        
        # Process bars
        for idx, bar in bars.iterrows():
            self._process_bar(bar, bars, idx)
        
        # Finalize
        self._finalize_session()
        
        logger.info(
            f"Backtest complete: {len(self.completed_trades)} trades, "
            f"{self.cumulative_r:.2f}R"
        )
        
        return self._build_results()
    
    def _initialize_session(self, start_ts: datetime, instrument: str, session_date: str):
        """Initialize for new session."""
        # Reset state
        self.active_trades = {}
        
        # Initialize builders (will be created on first bar)
        self.or_builder = None
        self.auction_builder = None
        self.feature_builder = FeatureTableBuilder(instrument, session_date)
        
        # Reset playbook state
        for playbook in self.playbooks:
            if hasattr(playbook, 'reset_session'):
                playbook.reset_session()
    
    def _process_bar(self, bar: pd.Series, bars_df: pd.DataFrame, idx: int):
        """Process single bar."""
        timestamp = bar["timestamp_utc"]
        
        # Initialize OR builder on first bar
        if self.or_builder is None:
            # Estimate ATR from bars (simplified - use recent range)
            atr_14 = self._estimate_atr(bars_df, idx)
            atr_60 = atr_14 * 1.2  # Rough estimate
            
            self.or_builder = DualORBuilder(
                start_ts=timestamp,
                micro_minutes=self.config.micro_minutes,
                primary_base_minutes=self.config.primary_base_minutes,
                primary_min_minutes=self.config.primary_min_minutes,
                primary_max_minutes=self.config.primary_max_minutes,
                atr_14=atr_14,
                atr_60=atr_60,
                low_vol_threshold=self.config.low_vol_threshold,
                high_vol_threshold=self.config.high_vol_threshold,
            )
            
            self.auction_builder = AuctionMetricsBuilder(
                start_ts=timestamp,
                atr_14=atr_14,
                adr_20=atr_14 * 10,  # Rough estimate
            )
        
        # Update OR builders
        if not self.or_builder.both_finalized:
            self.or_builder.update(bar)
            self.or_builder.finalize_if_due(timestamp)
            
            # Add bar to auction builder during OR period
            if not self.or_builder.primary_finalized:
                self.auction_builder.add_bar(bar)
        
        # Update active trades
        for trade_id in list(self.active_trades.keys()):
            self._update_active_trade(trade_id, bar)
        
        # Check for new signals (only if OR finalized)
        if self.or_builder.primary_finalized and len(self.active_trades) == 0:
            self._check_for_signals(bar, bars_df, idx)
    
    def _estimate_atr(self, bars_df: pd.DataFrame, current_idx: int) -> float:
        """Estimate ATR from recent bars."""
        if current_idx < 14:
            # Use first 14 bars
            window = bars_df.iloc[:current_idx+1]
        else:
            window = bars_df.iloc[max(0, current_idx-14):current_idx+1]
        
        if len(window) < 2:
            return 1.0  # Default
        
        ranges = window["high"] - window["low"]
        atr = ranges.mean()
        
        return max(atr, 0.1)  # Minimum 0.1
    
    def _calculate_adx(self, bars_df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average Directional Index (ADX) for regime detection.
        
        Args:
            bars_df: DataFrame with OHLC data
            period: ADX period
            
        Returns:
            ADX value (0-100). Higher = stronger trend.
        """
        if len(bars_df) < period + 1:
            return 0.0
        
        # Calculate True Range (TR)
        high = bars_df['high'].values
        low = bars_df['low'].values
        close = bars_df['close'].values
        
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        
        # Calculate directional movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        # Smooth with EMA
        alpha = 1.0 / period
        atr = pd.Series(tr).ewm(alpha=alpha, adjust=False).mean().iloc[-1]
        plus_di = pd.Series(plus_dm).ewm(alpha=alpha, adjust=False).mean().iloc[-1] / atr * 100
        minus_di = pd.Series(minus_dm).ewm(alpha=alpha, adjust=False).mean().iloc[-1] / atr * 100
        
        # Calculate DX and ADX
        dx = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
        
        return float(dx)
    
    def _check_momentum_filter(self, bar: pd.Series, bars_df: pd.DataFrame, idx: int, direction: str, or_high: float, or_low: float) -> bool:
        """Check if breakout has sufficient momentum.
        
        🚀 PHASE 2B: Only trade breakouts with strong price velocity
        
        Args:
            bar: Current bar
            bars_df: Full bars DataFrame
            idx: Current index
            direction: 'long' or 'short'
            or_high: OR high level
            or_low: OR low level
            
        Returns:
            True if momentum is sufficient, False otherwise
        """
        if not self.config.use_momentum_filter:
            return True
        
        # Look back 3 bars to calculate velocity
        lookback = 3
        if idx < lookback:
            return False  # Not enough history
        
        recent_bars = bars_df.iloc[max(0, idx-lookback):idx+1]
        price_start = recent_bars.iloc[0]['close']
        price_end = bar['close']
        price_change = abs(price_end - price_start)
        
        # Calculate ATR for normalization
        atr = self._estimate_atr(bars_df, idx)
        
        # Velocity = price change per bar in ATR units
        velocity = (price_change / atr) / lookback
        
        if velocity < self.config.min_breakout_velocity:
            logger.debug(f"❌ Momentum filter: velocity {velocity:.3f} < {self.config.min_breakout_velocity:.3f}")
            return False
        
        logger.debug(f"✅ Momentum filter: velocity {velocity:.3f}")
        return True
    
    def _check_volume_confirmation(self, bar: pd.Series, bars_df: pd.DataFrame, idx: int) -> bool:
        """Check if breakout has volume confirmation.
        
        🚀 PHASE 2B: Require volume spike on breakout
        
        Args:
            bar: Current bar
            bars_df: Full bars DataFrame
            idx: Current index
            
        Returns:
            True if volume is sufficient, False otherwise
        """
        if not self.config.use_volume_confirmation:
            return True
        
        # Calculate average volume over last 20 bars
        lookback = 20
        if idx < lookback:
            return True  # Not enough history, allow trade
        
        recent_volume = bars_df.iloc[max(0, idx-lookback):idx]['volume'].mean()
        current_volume = bar['volume']
        
        if recent_volume == 0:
            return True  # Avoid division by zero
        
        volume_ratio = current_volume / recent_volume
        
        if volume_ratio < self.config.min_volume_ratio:
            logger.debug(f"❌ Volume filter: ratio {volume_ratio:.2f} < {self.config.min_volume_ratio:.2f}")
            return False
        
        logger.debug(f"✅ Volume filter: ratio {volume_ratio:.2f}")
        return True
    
    def _check_trend_alignment(self, bars_df: pd.DataFrame, idx: int, direction: str) -> bool:
        """Check if price is aligned with broader trend.
        
        🚀 PHASE 2B: Only trade with the trend
        
        Args:
            bars_df: Full bars DataFrame
            idx: Current index
            direction: 'long' or 'short'
            
        Returns:
            True if trend is aligned, False otherwise
        """
        if not self.config.use_trend_alignment:
            return True
        
        # Need enough bars for slow EMA
        if idx < self.config.slow_ema_period:
            return True  # Not enough history
        
        # Calculate EMAs
        recent_bars = bars_df.iloc[:idx+1]
        closes = recent_bars['close']
        
        fast_ema = closes.ewm(span=self.config.fast_ema_period, adjust=False).mean().iloc[-1]
        slow_ema = closes.ewm(span=self.config.slow_ema_period, adjust=False).mean().iloc[-1]
        
        # Check alignment
        if direction == "long":
            if fast_ema <= slow_ema:
                logger.debug(f"❌ Trend filter: LONG but fast EMA ({fast_ema:.2f}) <= slow EMA ({slow_ema:.2f})")
                return False
        else:  # short
            if fast_ema >= slow_ema:
                logger.debug(f"❌ Trend filter: SHORT but fast EMA ({fast_ema:.2f}) >= slow EMA ({slow_ema:.2f})")
                return False
        
        logger.debug(f"✅ Trend filter: {direction.upper()} aligned")
        return True
    
    def _check_price_action_quality(self, bar: pd.Series) -> bool:
        """Check if price action is clean (no excessive wicks).
        
        🚀 PHASE 2B: Avoid choppy, indecisive candles
        
        Args:
            bar: Current bar
            
        Returns:
            True if price action is clean, False otherwise
        """
        if not self.config.use_price_action_filter:
            return True
        
        candle_range = abs(bar['high'] - bar['low'])
        if candle_range == 0:
            return False  # Doji, skip
        
        body_size = abs(bar['close'] - bar['open'])
        
        # Calculate wick sizes
        if bar['close'] > bar['open']:  # Green candle
            upper_wick = bar['high'] - bar['close']
            lower_wick = bar['open'] - bar['low']
        else:  # Red candle
            upper_wick = bar['high'] - bar['open']
            lower_wick = bar['close'] - bar['low']
        
        max_wick = max(upper_wick, lower_wick)
        wick_ratio = max_wick / candle_range
        
        if wick_ratio > self.config.max_wick_ratio:
            logger.debug(f"❌ Price action filter: wick ratio {wick_ratio:.2f} > {self.config.max_wick_ratio:.2f}")
            return False
        
        logger.debug(f"✅ Price action filter: clean candle (wick {wick_ratio:.2f})")
        return True
    
    def _check_reentry_cooldown(self, timestamp: pd.Timestamp, direction: str) -> bool:
        """Check if enough time has passed since last trade in this direction.
        
        🚀 PHASE 2B: Prevent overtrading
        
        Args:
            timestamp: Current timestamp
            direction: 'long' or 'short'
            
        Returns:
            True if cooldown passed, False otherwise
        """
        if not self.config.use_reentry_cooldown:
            return True
        
        last_time = self.last_trade_time[direction]
        if last_time is None:
            return True  # No previous trade
        
        minutes_since = (timestamp - last_time).total_seconds() / 60
        
        if minutes_since < self.config.reentry_cooldown_minutes:
            logger.debug(f"❌ Cooldown: {minutes_since:.1f}min < {self.config.reentry_cooldown_minutes}min since last {direction.upper()}")
            return False
        
        logger.debug(f"✅ Cooldown: {minutes_since:.1f}min passed")
        return True
    
    def _is_filtered_time(self, timestamp: pd.Timestamp, or_end_ts: pd.Timestamp) -> bool:
        """Check if current time should be filtered out.
        
        ✨ PHASE 1 OPTIMIZATION: Time-based filters
        
        Args:
            timestamp: Current bar timestamp
            or_end_ts: OR close timestamp
            
        Returns:
            True if time should be filtered (no trades), False otherwise
        """
        if not self.config.use_time_filters:
            return False
        
        # Filter 1: First N minutes after OR close
        minutes_since_or = (timestamp - or_end_ts).total_seconds() / 60
        if 0 <= minutes_since_or < self.config.avoid_first_minutes_after_or:
            return True
        
        # Filter 2: Lunch chop (11:30 CT - 13:00 CT)
        hour = timestamp.hour
        minute = timestamp.minute
        
        lunch_start_minutes = self.config.lunch_start_hour * 60 + self.config.lunch_start_minute
        lunch_end_minutes = self.config.lunch_end_hour * 60 + self.config.lunch_end_minute
        current_minutes = hour * 60 + minute
        
        if lunch_start_minutes <= current_minutes < lunch_end_minutes:
            return True
        
        return False
    
    def _check_for_signals(self, bar: pd.Series, bars_df: pd.DataFrame, idx: int):
        """Check all playbooks for signals."""
        # 🎯 PHASE 2: Check daily loss limit
        if self.daily_shutdown:
            logger.debug(f"Daily shutdown active (hit loss limit), skipping signals")
            return
        
        # Get OR state
        dual_or = self.or_builder.state()
        
        # 🎯 PHASE 2: Intraday monitor - stop if bleeding by noon
        if self.config.use_intraday_monitor and dual_or.primary_finalized:
            current_hour = bar["timestamp_utc"].hour
            if current_hour >= self.config.intraday_check_hour:
                if self.daily_r <= self.config.intraday_stop_loss_r:
                    if not self.daily_shutdown:
                        self.daily_shutdown = True
                        logger.warning(
                            f"🛑 INTRADAY STOP: Down {self.daily_r:.2f}R by {current_hour}:00. "
                            f"Shutting down for rest of day."
                        )
                    return
        
        # ✨ PHASE 1 OPTIMIZATION: Time filters
        if dual_or.primary_finalized and self._is_filtered_time(bar["timestamp_utc"], dual_or.primary_end_ts):
            logger.debug(f"Filtered time period, skipping signals")
            return
        
        # 🎯 PHASE 2: OR width filter - skip low volatility days
        # Using normalized width (width / ATR) - if < 0.4, skip session
        if self.config.use_or_width_filter and dual_or.primary_finalized:
            if dual_or.primary_width_norm is not None:
                min_norm_width = 0.4  # Minimum normalized width (40% of ATR)
                if dual_or.primary_width_norm < min_norm_width:
                    logger.info(
                        f"OR width too low (norm={dual_or.primary_width_norm:.2f} < "
                        f"{min_norm_width:.2f}), skipping low volatility session"
                    )
                    # Set shutdown flag to avoid checking every bar
                    self.daily_shutdown = True
                    return
        
        # Compute auction metrics (if not already)
        if not hasattr(self, '_auction_metrics'):
            self._auction_metrics = self.auction_builder.compute()
            
            # Classify state
            self._state_classification = classify_auction_state(
                self._auction_metrics,
                dual_or
            )
            
            logger.info(
                f"Auction classified: {self._state_classification.state.value} "
                f"(conf={self._state_classification.confidence:.2f})"
            )
            
            # 🎯 PHASE 2: Calculate ADX for regime filter
            if self.config.use_regime_filter:
                # Use bars up to current point for ADX
                bars_so_far = bars_df.iloc[:idx+1]
                adx = self._calculate_adx(bars_so_far, period=self.config.adx_period)
                
                if adx < self.config.adx_trending_threshold:
                    logger.warning(
                        f"🌊 CHOPPY REGIME DETECTED: ADX={adx:.1f} < {self.config.adx_trending_threshold:.1f}. "
                        f"Shutting down for rest of day."
                    )
                    self.daily_shutdown = True
                    return
                else:
                    logger.info(f"✅ TRENDING REGIME: ADX={adx:.1f}")
            
            # Cache ADX for later use
            self._session_adx = adx if self.config.use_regime_filter else None
        
        # Build context
        context = self._build_context(bar, dual_or, bars_df, idx)
        
        # Check context exclusion
        if self.exclusion_matrix is not None:
            signature = self.exclusion_matrix.create_signature(
                or_width_norm=dual_or.primary_width_norm or 1.0,
                breakout_delay=(bar["timestamp_utc"] - dual_or.primary_end_ts).seconds / 60,
                volume_quality=context.get("volume_quality_score", 0.5),
                auction_state=self._state_classification.state.value,
                gap_type=self._auction_metrics.gap_type.value,
            )
            
            if self.exclusion_matrix.is_excluded(signature):
                logger.debug("Context excluded, skipping signals")
                return
        
        # Check each playbook
        for playbook in self.playbooks:
            if not playbook.is_eligible(context):
                continue
            
            signals = playbook.generate_signals(context)
            
            for signal in signals:
                # Apply probability gate if enabled
                if self.prob_gate is not None:
                    p_ext = 0.5  # Default (no model yet)
                    gated = self.prob_gate.evaluate(signal, p_ext)
                    
                    if not gated.passed_gate:
                        logger.debug(f"Signal rejected by prob gate: {gated.rejection_reason}")
                        continue
                else:
                    gated = None
                
                # 🚀 PHASE 2B: ENTRY QUALITY FILTERS
                # Check cooldown
                if not self._check_reentry_cooldown(bar["timestamp_utc"], signal.direction):
                    logger.debug(f"Signal rejected: cooldown not passed")
                    continue
                
                # Check momentum
                if not self._check_momentum_filter(bar, bars_df, idx, signal.direction, dual_or.primary_high, dual_or.primary_low):
                    logger.debug(f"Signal rejected: insufficient momentum")
                    continue
                
                # Check volume
                if not self._check_volume_confirmation(bar, bars_df, idx):
                    logger.debug(f"Signal rejected: insufficient volume")
                    continue
                
                # Check trend alignment
                if not self._check_trend_alignment(bars_df, idx, signal.direction):
                    logger.debug(f"Signal rejected: trend not aligned")
                    continue
                
                # Check price action quality
                if not self._check_price_action_quality(bar):
                    logger.debug(f"Signal rejected: poor price action")
                    continue
                
                logger.info(f"✅ Signal passed ALL quality filters: {signal.direction.upper()} @ {signal.entry_price:.2f}")
                
                # Create trade
                self._create_trade(signal, dual_or, gated)
                
                # Update last trade time
                self.last_trade_time[signal.direction] = bar["timestamp_utc"]
                
                break  # Only one trade at a time
    
    def _build_context(
        self,
        bar: pd.Series,
        dual_or,
        bars_df: pd.DataFrame,
        idx: int
    ) -> Dict:
        """Build context dictionary for playbooks."""
        atr_14 = self._estimate_atr(bars_df, idx)
        
        context = {
            "current_bar": bar,
            "current_price": bar["close"],
            "timestamp": bar["timestamp_utc"],
            "instrument": "ES",  # TODO: pass through
            
            # OR
            "or_primary_high": dual_or.primary_high,
            "or_primary_low": dual_or.primary_low,
            "or_primary_finalized": dual_or.primary_finalized,
            "or_primary_valid": dual_or.primary_valid,
            "or_primary_width_norm": dual_or.primary_width_norm or 1.0,
            
            # Auction
            "auction_state": self._state_classification.state.value,
            "auction_state_confidence": self._state_classification.confidence,
            "drive_energy": self._auction_metrics.drive_energy,
            "rotations": self._auction_metrics.rotations,
            "vol_z": self._auction_metrics.volume_z,
            "gap_type": self._auction_metrics.gap_type.value,
            
            # Metrics
            "atr_14": atr_14,
            "breakout_delay_minutes": (bar["timestamp_utc"] - dual_or.primary_end_ts).seconds / 60,
            "volume_quality_score": 0.5,  # Simplified
            "normalized_vol": 1.0,  # Simplified
            "recent_return_std": 0.02,  # Simplified
            
            # Exclusion
            "context_excluded": False,
            
            # Stop parameters (from MFE/MAE analysis if available)
            "phase1_stop_distance": atr_14 * 0.8,  # 80th percentile winner MAE
        }
        
        return context
    
    def _create_trade(self, signal, dual_or, gated_result=None):
        """Create new trade from signal."""
        trade_id = f"{signal.playbook_name}_{signal.timestamp.strftime('%H%M%S')}"
        
        # Initialize risk managers
        initial_risk = abs(signal.entry_price - signal.initial_stop)
        
        # Two-phase stop ✨ with Phase 1 optimizations
        stop_mgr = TwoPhaseStopManager(
            direction=signal.direction,
            entry_price=signal.entry_price,
            initial_risk=initial_risk,
            phase1_stop_distance=signal.phase1_stop_distance,
            phase2_trigger_r=self.config.phase2_trigger_r,
            structural_anchor=signal.structural_anchor,
            stop_multiplier=self.config.stop_multiplier,  # ✨ Widen stops
            breakeven_trigger_r=self.config.breakeven_trigger_r,  # ✨ Breakeven at +0.3R
        ) if self.config.use_two_phase_stops else None
        
        # Salvage
        salvage_mgr = SalvageManager(
            direction=signal.direction,
            entry_price=signal.entry_price,
            initial_risk=initial_risk,
            initial_stop=signal.initial_stop,
        ) if self.config.use_salvage else None
        
        # ✨ Partial exits (Phase 1 optimization)
        partial_mgr = None
        if self.config.use_partial_exits:
            from orb_confluence.risk.partial_exits import PartialExitManager, PartialTarget
            partial_mgr = PartialExitManager(
                direction=signal.direction,
                entry_price=signal.entry_price,
                initial_risk=initial_risk,
                targets=[
                    PartialTarget(target_r=self.config.partial_target_1_r, size_fraction=self.config.partial_target_1_size),
                    PartialTarget(target_r=self.config.partial_target_2_r, size_fraction=self.config.partial_target_2_size),
                ],
            )
        
        # MFE/MAE tracker
        mfe_mae_tracker = MFEMAETracker(
            trade_id=trade_id,
            direction=signal.direction,
            entry_price=signal.entry_price,
            initial_stop=signal.initial_stop,
            entry_timestamp=signal.timestamp,
            tags={
                "playbook": signal.playbook_name,
                "auction_state": signal.metadata.auction_state if signal.metadata else "UNKNOWN",
            },
        )
        
        # Store trade state
        self.active_trades[trade_id] = {
            "signal": signal,
            "stop_mgr": stop_mgr,
            "salvage_mgr": salvage_mgr,
            "partial_mgr": partial_mgr,  # ✨ Track partial exits
            "mfe_mae_tracker": mfe_mae_tracker,
            "gated_result": gated_result,
            "bars_in_trade": 0,
        }
        
        logger.info(
            f"Trade opened: {trade_id} {signal.direction.upper()} @ {signal.entry_price:.2f}, "
            f"stop={signal.initial_stop:.2f}, playbook={signal.playbook_name}"
        )
    
    def _update_active_trade(self, trade_id: str, bar: pd.Series):
        """Update active trade with new bar."""
        trade_state = self.active_trades[trade_id]
        signal = trade_state["signal"]
        stop_mgr = trade_state["stop_mgr"]
        salvage_mgr = trade_state["salvage_mgr"]
        mfe_mae_tracker = trade_state["mfe_mae_tracker"]
        
        trade_state["bars_in_trade"] += 1
        
        # Update MFE/MAE
        mfe_mae_tracker.update(bar)
        
        # Compute current R
        initial_risk = abs(signal.entry_price - signal.initial_stop)
        if signal.direction == "long":
            current_r = (bar["close"] - signal.entry_price) / initial_risk
        else:
            current_r = (signal.entry_price - bar["close"]) / initial_risk
        
        # Check salvage
        if salvage_mgr:
            salvage_event = salvage_mgr.evaluate(
                current_price=bar["close"],
                current_mfe_r=mfe_mae_tracker.mfe_r,
                current_r=current_r,
                timestamp=bar["timestamp_utc"],
            )
            
            if salvage_event:
                self._close_trade(trade_id, bar, "SALVAGE", salvage_event.current_r)
                return
        
        # Update stops
        if stop_mgr:
            stop_update = stop_mgr.update(
                current_price=bar["close"],
                current_mfe_r=mfe_mae_tracker.mfe_r,
                timestamp=bar["timestamp_utc"],
            )
            
            if stop_update:
                logger.debug(f"Stop updated: {stop_update}")
        
        # Check stop hit
        current_stop = stop_mgr.stop_price if stop_mgr else signal.initial_stop
        
        if signal.direction == "long":
            stop_hit = bar["low"] <= current_stop
        else:
            stop_hit = bar["high"] >= current_stop
        
        if stop_hit:
            exit_price = current_stop
            exit_r = (exit_price - signal.entry_price) / initial_risk
            if signal.direction == "short":
                exit_r = -exit_r
            
            self._close_trade(trade_id, bar, "STOP", exit_r)
            return
        
        # ✨ Check partial exits (Phase 1 optimization)
        partial_mgr = trade_state.get("partial_mgr")
        if partial_mgr:
            partial_fills = partial_mgr.check_targets(
                current_price=bar["close"],
                bar_high=bar["high"],
                bar_low=bar["low"],
                timestamp=bar["timestamp_utc"],
            )
            
            if partial_fills:
                for fill in partial_fills:
                    logger.info(f"Partial exit: {fill}")
                    # Track partial fills for reporting
                    if "partial_fills" not in trade_state:
                        trade_state["partial_fills"] = []
                    trade_state["partial_fills"].append(fill)
                    
                    # ✨ PHASE 1.1: Trail stop after first partial to lock in gains
                    if fill.target_number == 1 and stop_mgr:
                        # After first partial (+0.75R), trail stop to +0.5R
                        trail_to_r = 0.5
                        trail_price = signal.entry_price + (trail_to_r * initial_risk)
                        if signal.direction == "short":
                            trail_price = signal.entry_price - (trail_to_r * initial_risk)
                        
                        # Only move stop if it's better than current
                        if signal.direction == "long" and trail_price > stop_mgr.current_stop:
                            stop_mgr.current_stop = trail_price
                            logger.info(f"Trailing stop after partial: {trail_price:.2f} (+{trail_to_r}R)")
                        elif signal.direction == "short" and trail_price < stop_mgr.current_stop:
                            stop_mgr.current_stop = trail_price
                            logger.info(f"Trailing stop after partial: {trail_price:.2f} (+{trail_to_r}R)")
            
            # Close trade if all targets hit (remaining size = 0)
            if partial_mgr.all_targets_hit:
                # Calculate weighted average realized R
                total_realized_r = sum(
                    fill.realized_r * fill.size_fraction
                    for fill in trade_state.get("partial_fills", [])
                )
                self._close_trade(trade_id, bar, "TARGET", total_realized_r)
                return
        else:
            # Fallback: single target at 1.5R
            target_r = 1.5
            if mfe_mae_tracker.mfe_r >= target_r:
                self._close_trade(trade_id, bar, "TARGET", target_r)
                return
    
    def _close_trade(self, trade_id: str, bar: pd.Series, reason: str, realized_r: float):
        """Close trade and record results."""
        trade_state = self.active_trades[trade_id]
        signal = trade_state["signal"]
        stop_mgr = trade_state["stop_mgr"]
        salvage_mgr = trade_state["salvage_mgr"]
        mfe_mae_tracker = trade_state["mfe_mae_tracker"]
        
        # Finalize MFE/MAE tracking
        initial_risk = abs(signal.entry_price - signal.initial_stop)
        if signal.direction == "long":
            exit_price = signal.entry_price + (realized_r * initial_risk)
        else:
            exit_price = signal.entry_price - (realized_r * initial_risk)
        
        analysis = mfe_mae_tracker.finalize(exit_price, reason)
        
        # Create trade record
        trade = ORB2Trade(
            trade_id=trade_id,
            playbook_name=signal.playbook_name,
            direction=signal.direction,
            entry_timestamp=signal.timestamp,
            entry_price=signal.entry_price,
            exit_timestamp=bar["timestamp_utc"],
            exit_price=exit_price,
            exit_reason=reason,
            realized_r=realized_r,
            mfe_r=analysis.mfe_r,
            mae_r=analysis.mae_r,
            auction_state=signal.metadata.auction_state if signal.metadata else "UNKNOWN",
            or_width_norm=signal.metadata.or_width_norm if signal.metadata else 0.0,
            initial_stop=signal.initial_stop,
            final_stop=stop_mgr.stop_price if stop_mgr else signal.initial_stop,
            stop_phase=stop_mgr.phase.value if stop_mgr else "PHASE1",
            salvage_triggered=(reason == "SALVAGE"),
        )
        
        self.completed_trades.append(trade)
        self.cumulative_r += realized_r
        
        # 🎯 PHASE 2: Update daily P&L and check loss limit
        self.daily_r += realized_r
        if self.config.use_daily_loss_limit and self.daily_r <= self.config.daily_loss_limit_r:
            self.daily_shutdown = True
            logger.warning(
                f"🚨 DAILY LOSS LIMIT HIT: {self.daily_r:.2f}R / {self.config.daily_loss_limit_r:.2f}R limit. "
                f"Shutting down for rest of day."
            )
        
        # Remove from active
        del self.active_trades[trade_id]
        
        logger.info(
            f"Trade closed: {trade_id} {reason}, "
            f"R={realized_r:.2f}, MFE={analysis.mfe_r:.2f}, MAE={analysis.mae_r:.2f}, "
            f"daily={self.daily_r:.2f}R, cumulative={self.cumulative_r:.2f}R"
        )
    
    def _finalize_session(self):
        """Finalize session (close any remaining trades)."""
        for trade_id in list(self.active_trades.keys()):
            logger.warning(f"Force closing trade at EOD: {trade_id}")
            # Get last bar approximation
            trade_state = self.active_trades[trade_id]
            signal = trade_state["signal"]
            # Close at breakeven
            self._close_trade(trade_id, {"timestamp_utc": datetime.now(), "close": signal.entry_price}, "EOD", 0.0)
    
    def _build_results(self) -> Dict:
        """Build results dictionary."""
        if not self.completed_trades:
            return {
                "total_trades": 0,
                "cumulative_r": 0.0,
                "trades": [],
            }
        
        # Calculate metrics
        r_values = [t.realized_r for t in self.completed_trades]
        winning_trades = [t for t in self.completed_trades if t.realized_r > 0]
        losing_trades = [t for t in self.completed_trades if t.realized_r < 0]
        
        return {
            "total_trades": len(self.completed_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / len(self.completed_trades),
            "cumulative_r": self.cumulative_r,
            "expectancy": np.mean(r_values),
            "avg_winner": np.mean([t.realized_r for t in winning_trades]) if winning_trades else 0.0,
            "avg_loser": np.mean([t.realized_r for t in losing_trades]) if losing_trades else 0.0,
            "max_win": max(r_values),
            "max_loss": min(r_values),
            "avg_mfe": np.mean([t.mfe_r for t in self.completed_trades]),
            "avg_mae": np.mean([t.mae_r for t in self.completed_trades]),
            "salvage_count": sum(1 for t in self.completed_trades if t.salvage_triggered),
            "trades": self.completed_trades,
            
            # By playbook
            "trades_by_playbook": {
                playbook.name: len([t for t in self.completed_trades if t.playbook_name == playbook.name])
                for playbook in self.playbooks
            },
            
            # By state
            "trades_by_state": {
                state: len([t for t in self.completed_trades if t.auction_state == state])
                for state in set(t.auction_state for t in self.completed_trades)
            },
        }

