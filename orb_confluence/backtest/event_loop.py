"""Event-driven backtest engine for ORB strategy.

Orchestrates bar-by-bar simulation with full state management across
all strategy components (OR, factors, scoring, breakout, trades, governance).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from ..config.schema import StrategyConfig
from ..features import (
    OpeningRangeBuilder,
    validate_or,
    RelativeVolume,
    analyze_price_action,
    ProfileProxy,
    SessionVWAP,
    ADX,
)
from ..strategy import (
    compute_score,
    detect_breakout,
    TradeSignal,
    ActiveTrade,
    compute_stop,
    build_targets,
    TradeManager,
    GovernanceManager,
    TradeEvent,
)


@dataclass
class FactorSnapshot:
    """Snapshot of factor values at a point in time.
    
    Attributes:
        timestamp: Snapshot timestamp
        or_finalized: Whether OR is finalized
        or_high: OR high (if finalized)
        or_low: OR low (if finalized)
        rel_vol: Relative volume
        price_action_long: Price action long flag
        price_action_short: Price action short flag
        profile_long: Profile long flag
        profile_short: Profile short flag
        vwap: VWAP value
        adx: ADX value
        confluence_score_long: Long confluence score
        confluence_score_short: Short confluence score
    """
    
    timestamp: datetime
    or_finalized: bool
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    rel_vol: Optional[float] = None
    price_action_long: Optional[bool] = None
    price_action_short: Optional[bool] = None
    profile_long: Optional[bool] = None
    profile_short: Optional[bool] = None
    vwap: Optional[float] = None
    adx: Optional[float] = None
    confluence_score_long: Optional[float] = None
    confluence_score_short: Optional[float] = None


@dataclass
class BacktestResult:
    """Results from event loop backtest.
    
    Attributes:
        trades: List of completed trades
        equity_curve: DataFrame with timestamp and cumulative R
        factor_snapshots: List of factor snapshots (sampled)
        daily_stats: Dictionary of daily statistics
        governance_events: List of governance events (lockouts, caps)
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        total_r: Total R-multiple achieved
        max_drawdown_r: Maximum drawdown in R
        final_equity_r: Final equity in R
    """
    
    trades: List[ActiveTrade]
    equity_curve: pd.DataFrame
    factor_snapshots: List[FactorSnapshot]
    daily_stats: Dict[datetime.date, dict]
    governance_events: List[dict]
    
    # Summary statistics
    total_trades: int = 0
    winning_trades: int = 0
    total_r: float = 0.0
    max_drawdown_r: float = 0.0
    final_equity_r: float = 0.0
    
    def __post_init__(self):
        """Calculate summary statistics."""
        if self.trades:
            self.total_trades = len(self.trades)
            self.winning_trades = sum(1 for t in self.trades if t.realized_r and t.realized_r > 0)
            self.total_r = sum(t.realized_r for t in self.trades if t.realized_r)
        
        if not self.equity_curve.empty:
            self.final_equity_r = self.equity_curve['cumulative_r'].iloc[-1]
            
            # Calculate max drawdown
            running_max = self.equity_curve['cumulative_r'].cummax()
            drawdown = self.equity_curve['cumulative_r'] - running_max
            self.max_drawdown_r = drawdown.min()


class EventLoopBacktest:
    """Event-driven backtest engine.
    
    Processes bars sequentially, updating all components and tracking state.
    
    Example:
        >>> from orb_confluence.config import load_config
        >>> from orb_confluence.data import SyntheticProvider
        >>> 
        >>> config = load_config("config.yaml")
        >>> bars = SyntheticProvider().generate_synthetic_day(seed=42)
        >>> 
        >>> engine = EventLoopBacktest(config)
        >>> result = engine.run(bars)
        >>> 
        >>> print(f"Trades: {result.total_trades}")
        >>> print(f"Total R: {result.total_r:.2f}")
        >>> print(f"Win rate: {result.winning_trades / result.total_trades:.1%}")
    """
    
    def __init__(
        self,
        config: StrategyConfig,
        sample_factors_every_n: int = 10,
    ):
        """Initialize backtest engine.
        
        Args:
            config: Strategy configuration.
            sample_factors_every_n: Sample factor snapshots every N bars (0 = all).
        """
        self.config = config
        self.sample_factors_every_n = sample_factors_every_n
        
        # State components (initialized in run)
        self.or_builder: Optional[OpeningRangeBuilder] = None
        self.rel_vol: Optional[RelativeVolume] = None
        self.profile_proxy: Optional[ProfileProxy] = None
        self.vwap: Optional[SessionVWAP] = None
        self.adx: Optional[ADX] = None
        self.trade_manager: Optional[TradeManager] = None
        self.governance: Optional[GovernanceManager] = None
        
        # Active state
        self.active_trade: Optional[ActiveTrade] = None
        self.last_signal_timestamp: Optional[datetime] = None
        
        # Factor state cache
        self.rel_vol_state: Dict = {}
        self.vwap_state: Dict = {}
        self.adx_state: Dict = {}
        
        # Results collection
        self.completed_trades: List[ActiveTrade] = []
        self.equity_curve_records: List[dict] = []
        self.factor_snapshots: List[FactorSnapshot] = []
        self.governance_events: List[dict] = []
        self.daily_stats: Dict[datetime.date, dict] = {}
        
        self.cumulative_r: float = 0.0
        self.bar_counter: int = 0
    
    def run(self, bars: pd.DataFrame) -> BacktestResult:
        """Run backtest on bar data.
        
        Args:
            bars: DataFrame with columns: timestamp_utc, open, high, low, close, volume.
            
        Returns:
            BacktestResult with trades, equity curve, and statistics.
        """
        logger.info(f"Starting backtest: {len(bars)} bars")
        
        # Initialize components
        self._initialize_components()
        
        # Process bars
        for idx, bar in bars.iterrows():
            self._process_bar(bar)
        
        # Finalize
        result = self._finalize_backtest()
        
        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"{result.total_r:.2f}R, "
            f"max DD {result.max_drawdown_r:.2f}R"
        )
        
        return result
    
    def _initialize_components(self) -> None:
        """Initialize all strategy components."""
        # OR builder (will be created on first bar)
        self.or_builder = None
        
        # Factors
        self.rel_vol = RelativeVolume(
            lookback=self.config.factors.rel_volume.lookback,
            min_history=self.config.factors.rel_volume.lookback + 5,
        )
        
        self.profile_proxy = ProfileProxy()
        
        self.vwap = SessionVWAP()
        
        self.adx = ADX(period=self.config.factors.adx.period)
        
        # Trade manager
        self.trade_manager = TradeManager(
            conservative_fills=True,
            move_be_at_r=self.config.trade.move_be_at_r,
            be_buffer=self.config.trade.be_buffer,
        )
        
        # Governance
        self.governance = GovernanceManager(
            max_signals_per_day=self.config.governance.max_signals_per_day,
            lockout_after_losses=self.config.governance.lockout_after_losses,
            time_cutoff=None,  # TODO: parse from config if needed
        )
        
        # Reset state
        self.active_trade = None
        self.last_signal_timestamp = None
        self.completed_trades = []
        self.equity_curve_records = []
        self.factor_snapshots = []
        self.governance_events = []
        self.daily_stats = {}
        self.cumulative_r = 0.0
        self.bar_counter = 0
        
        logger.debug("Components initialized")
    
    def _process_bar(self, bar: pd.Series) -> None:
        """Process single bar through event loop.
        
        Args:
            bar: Bar data with timestamp_utc, open, high, low, close, volume.
        """
        self.bar_counter += 1
        timestamp = bar['timestamp_utc']
        
        # Initialize OR builder on first bar
        if self.or_builder is None:
            self.or_builder = OpeningRangeBuilder(
                start_ts=timestamp,
                duration_minutes=self.config.orb.base_minutes,
            )
            self.vwap.reset()
            logger.debug(f"OR builder initialized at {timestamp}")
        
        # Update OR builder (only if not finalized)
        or_was_finalized = self.or_builder.is_finalized
        if not or_was_finalized:
            self.or_builder.update(bar)
            self.or_builder.finalize_if_due(timestamp)
        
        # If OR just finalized, validate it
        or_state = self.or_builder.state()
        if or_state.finalized and not or_was_finalized:
            # Validate OR (would need ATR value - simplified here)
            # In real implementation, calculate ATR from prior bars
            logger.info(
                f"OR finalized: high={or_state.high:.2f}, low={or_state.low:.2f}, "
                f"width={or_state.width:.2f}"
            )
        
        # Update factors
        self._update_factors(bar)
        
        # Sample factor snapshot if needed
        if self.sample_factors_every_n == 0 or self.bar_counter % self.sample_factors_every_n == 0:
            snapshot = self._create_factor_snapshot(bar, or_state)
            self.factor_snapshots.append(snapshot)
        
        # If OR not finalized, skip signal logic
        if not or_state.finalized or not or_state.valid:
            self._update_equity_curve(timestamp)
            return
        
        # Update active trade if exists
        if self.active_trade is not None:
            self._update_active_trade(bar)
        
        # Check for new signal (only if no active trade)
        if self.active_trade is None:
            self._check_for_signal(bar, or_state)
        
        # Update equity curve
        self._update_equity_curve(timestamp)
    
    def _update_factors(self, bar: pd.Series) -> None:
        """Update all factor modules.
        
        Args:
            bar: Current bar.
        """
        # Relative volume
        self.rel_vol_state = self.rel_vol.update(bar['volume'])
        
        # VWAP
        typical_price = (bar['high'] + bar['low'] + bar['close']) / 3
        self.vwap_state = self.vwap.update(typical_price, bar['volume'])
        
        # ADX
        self.adx_state = self.adx.update(bar['high'], bar['low'], bar['close'])
    
    def _create_factor_snapshot(
        self,
        bar: pd.Series,
        or_state,
    ) -> FactorSnapshot:
        """Create factor snapshot for current bar.
        
        Args:
            bar: Current bar.
            or_state: OR state.
            
        Returns:
            FactorSnapshot.
        """
        # Get factor values
        rel_vol_data = self.rel_vol_state
        vwap_data = self.vwap_state
        adx_data = self.adx_state
        
        # Price action (would need bar history - simplified)
        price_action_long = False
        price_action_short = False
        
        # Profile proxy (would need prior day data - simplified)
        profile_long = False
        profile_short = False
        
        # Confluence scores (if OR finalized)
        confluence_long = None
        confluence_short = None
        
        if or_state.finalized:
            factor_flags = {
                'rel_vol': 1.0 if rel_vol_data.get('spike_flag') else 0.0,
                'price_action': 1.0 if price_action_long or price_action_short else 0.0,
                'profile': 1.0 if profile_long or profile_short else 0.0,
                'vwap': 0.0,
                'adx': 0.0,
            }
            
            # Compute scores
            score_long, req_long, _ = compute_score(
                direction='long',
                factor_flags=factor_flags,
                weights=self.config.scoring.weights,
                trend_weak=adx_data.get('trend_weak', False),
                base_required=self.config.scoring.base_required,
                weak_trend_required=self.config.scoring.weak_trend_required,
            )
            
            score_short, req_short, _ = compute_score(
                direction='short',
                factor_flags=factor_flags,
                weights=self.config.scoring.weights,
                trend_weak=adx_data.get('trend_weak', False),
                base_required=self.config.scoring.base_required,
                weak_trend_required=self.config.scoring.weak_trend_required,
            )
            
            confluence_long = score_long
            confluence_short = score_short
        
        return FactorSnapshot(
            timestamp=bar['timestamp_utc'],
            or_finalized=or_state.finalized,
            or_high=or_state.high if or_state.finalized else None,
            or_low=or_state.low if or_state.finalized else None,
            rel_vol=rel_vol_data.get('rel_vol'),
            price_action_long=price_action_long,
            price_action_short=price_action_short,
            profile_long=profile_long,
            profile_short=profile_short,
            vwap=vwap_data.get('vwap'),
            adx=adx_data.get('adx_value'),
            confluence_score_long=confluence_long,
            confluence_score_short=confluence_short,
        )
    
    def _check_for_signal(self, bar: pd.Series, or_state) -> None:
        """Check for breakout signal.
        
        Args:
            bar: Current bar.
            or_state: OR state.
        """
        # Check governance
        if not self.governance.can_emit_signal(bar['timestamp_utc']):
            return
        
        # Get factor flags (simplified - would use real factor analysis)
        factor_flags = {
            'rel_vol': 1.0 if self.rel_vol_state.get('spike_flag') else 0.0,
            'price_action': 0.0,  # Simplified
            'profile': 0.0,  # Simplified
            'vwap': 0.0,  # Simplified
            'adx': 0.0,  # Simplified
        }
        
        # Compute confluence for both directions
        adx_data = self.adx_state
        trend_weak = adx_data.get('trend_weak', False)
        
        score_long, req_long, pass_long = compute_score(
            direction='long',
            factor_flags=factor_flags,
            weights=self.config.scoring.weights,
            trend_weak=trend_weak,
            base_required=self.config.scoring.base_required,
            weak_trend_required=self.config.scoring.weak_trend_required,
        )
        
        score_short, req_short, pass_short = compute_score(
            direction='short',
            factor_flags=factor_flags,
            weights=self.config.scoring.weights,
            trend_weak=trend_weak,
            base_required=self.config.scoring.base_required,
            weak_trend_required=self.config.scoring.weak_trend_required,
        )
        
        # Calculate breakout triggers with buffer
        buffer = self.config.buffers.fixed  # Using fixed buffer for now
        upper_trigger = or_state.high + buffer
        lower_trigger = or_state.low - buffer
        
        # Detect breakout
        long_signal, short_signal = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=upper_trigger,
            lower_trigger=lower_trigger,
            confluence_long_pass=pass_long,
            confluence_short_pass=pass_short,
            confluence_long_score=score_long,
            confluence_short_score=score_short,
            confluence_required=max(req_long, req_short),
            lockout=False,  # Already checked governance
            last_signal_timestamp=self.last_signal_timestamp,
        )
        
        # Create trade if signal
        if long_signal:
            self._create_trade_from_signal(long_signal, or_state, score_long, req_long, factor_flags)
        elif short_signal:
            self._create_trade_from_signal(short_signal, or_state, score_short, req_short, factor_flags)
    
    def _create_trade_from_signal(
        self,
        signal,
        or_state,
        confluence_score: float,
        confluence_required: float,
        factor_flags: dict,
    ) -> None:
        """Create active trade from breakout signal.
        
        Args:
            signal: BreakoutSignal.
            or_state: OR state.
            confluence_score: Confluence score.
            confluence_required: Required score.
            factor_flags: Factor flags.
        """
        # Create TradeSignal
        trade_signal = TradeSignal(
            direction=signal.direction,
            timestamp=signal.timestamp,
            entry_price=signal.entry_price,
            confluence_score=confluence_score,
            confluence_required=confluence_required,
            factors=factor_flags,
            or_high=or_state.high,
            or_low=or_state.low,
            signal_id=f"{signal.direction.upper()}_{signal.timestamp.strftime('%Y%m%d_%H%M%S')}",
        )
        
        # Compute stop
        stop_price = compute_stop(
            signal_direction=signal.direction,
            entry_price=signal.entry_price,
            or_state=or_state,
            stop_mode=self.config.trade.stop_mode,
            extra_buffer=self.config.trade.extra_stop_buffer,
        )
        
        # Build targets
        targets = build_targets(
            entry_price=signal.entry_price,
            stop_price=stop_price,
            direction=signal.direction,
            partials=self.config.trade.partials,
            t1_r=self.config.trade.t1_r,
            t1_pct=self.config.trade.t1_pct,
            t2_r=self.config.trade.t2_r,
            t2_pct=self.config.trade.t2_pct,
            runner_r=self.config.trade.runner_r,
            primary_r=self.config.trade.primary_r,
        )
        
        # Create ActiveTrade
        self.active_trade = ActiveTrade(
            trade_id=trade_signal.signal_id,
            direction=signal.direction,
            entry_timestamp=signal.timestamp,
            entry_price=signal.entry_price,
            stop_price_initial=stop_price,
            stop_price_current=stop_price,
            targets=targets,
            signal=trade_signal,
        )
        
        # Register with governance
        self.governance.register_signal_emitted(signal.timestamp)
        self.last_signal_timestamp = signal.timestamp
        
        logger.info(
            f"Trade created: {self.active_trade.trade_id} "
            f"{signal.direction.upper()} @ {signal.entry_price:.2f}, "
            f"stop={stop_price:.2f}, score={confluence_score:.1f}/{confluence_required:.1f}"
        )
    
    def _update_active_trade(self, bar: pd.Series) -> None:
        """Update active trade with new bar.
        
        Args:
            bar: Current bar.
        """
        if self.active_trade is None:
            return
        
        # Update trade
        update = self.trade_manager.update(self.active_trade, bar)
        
        # Log events
        for event in update.events:
            if event == TradeEvent.PARTIAL_FILL:
                partial = self.active_trade.partials_filled[-1]
                logger.info(
                    f"Partial fill T{partial.target_number}: "
                    f"{partial.size_fraction:.0%} @ {partial.price:.2f} "
                    f"({partial.r_multiple:.2f}R)"
                )
            elif event == TradeEvent.BREAKEVEN_MOVE:
                logger.info(f"Stop moved to breakeven: {self.active_trade.stop_price_current:.2f}")
        
        # Check if closed
        if update.closed:
            self._finalize_trade(self.active_trade)
            self.active_trade = None
    
    def _finalize_trade(self, trade: ActiveTrade) -> None:
        """Finalize closed trade and update governance.
        
        Args:
            trade: Closed trade.
        """
        # Add to completed trades
        self.completed_trades.append(trade)
        
        # Update cumulative R
        self.cumulative_r += trade.realized_r
        
        # Register with governance
        win = trade.realized_r > 0
        full_stop = trade.exit_reason == 'stop' and len(trade.partials_filled) == 0
        
        self.governance.register_trade_outcome(win=win, full_stop_loss=full_stop)
        
        logger.info(
            f"Trade closed: {trade.trade_id} {trade.exit_reason.upper()}, "
            f"R={trade.realized_r:.2f}, cumulative={self.cumulative_r:.2f}R"
        )
        
        # Check for lockout
        if self.governance.state.lockout_active:
            self.governance_events.append({
                'timestamp': trade.exit_timestamp,
                'event': 'lockout',
                'reason': self.governance.state.lockout_reason,
            })
            logger.warning(f"LOCKOUT: {self.governance.state.lockout_reason}")
    
    def _update_equity_curve(self, timestamp: datetime) -> None:
        """Update equity curve with current state.
        
        Args:
            timestamp: Current timestamp.
        """
        self.equity_curve_records.append({
            'timestamp': timestamp,
            'cumulative_r': self.cumulative_r,
        })
    
    def _finalize_backtest(self) -> BacktestResult:
        """Finalize backtest and create result.
        
        Returns:
            BacktestResult.
        """
        # Build equity curve DataFrame
        equity_df = pd.DataFrame(self.equity_curve_records)
        
        # Build daily stats (simplified)
        for trade in self.completed_trades:
            trade_date = trade.entry_timestamp.date()
            if trade_date not in self.daily_stats:
                self.daily_stats[trade_date] = {
                    'trades': 0,
                    'wins': 0,
                    'total_r': 0.0,
                }
            
            self.daily_stats[trade_date]['trades'] += 1
            if trade.realized_r > 0:
                self.daily_stats[trade_date]['wins'] += 1
            self.daily_stats[trade_date]['total_r'] += trade.realized_r
        
        return BacktestResult(
            trades=self.completed_trades,
            equity_curve=equity_df,
            factor_snapshots=self.factor_snapshots,
            daily_stats=self.daily_stats,
            governance_events=self.governance_events,
        )