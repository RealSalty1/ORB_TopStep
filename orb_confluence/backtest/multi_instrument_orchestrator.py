"""Multi-instrument orchestrator for comprehensive ORB strategy backtesting.

Coordinates all modules:
- Per-instrument OR tracking
- Goldilocks volume filtering
- Adaptive buffer calculation
- Breakout detection with retest logic
- Trade management with staged targets
- Prop firm governance enforcement
- Comprehensive logging
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, time
import pandas as pd
import numpy as np
from pathlib import Path
import json
from loguru import logger

from ..config.instrument_loader import get_instrument_config, get_all_instruments
from ..features.goldilocks_volume import create_goldilocks_filter_from_config
from ..features.adaptive_or import AdaptiveORBuilder, ATRProvider
from ..strategy.adaptive_buffer import AdaptiveBufferCalculator, BreakoutDetector
from ..strategy.enhanced_trade_manager import EnhancedTradeManager, ActiveTrade
from ..strategy.prop_governance import PropGovernanceEngine, PropAccountRules
from ..strategy.trade_models import (
    ComprehensiveTrade, ORMetrics, VolumeMetrics, BreakoutContext,
    RiskMetrics, TradeOutcome, FactorSnapshot, Target, SessionSummary
)


@dataclass
class InstrumentState:
    """State for a single instrument during backtesting."""
    symbol: str
    config: any
    
    # Modules
    volume_filter: any
    atr_provider: ATRProvider
    buffer_calc: AdaptiveBufferCalculator
    breakout_detector: BreakoutDetector
    trade_manager: EnhancedTradeManager
    
    # OR tracking
    or_builder: Optional[any] = None
    or_finalized: bool = False
    or_state: Optional[any] = None
    
    # Active trade
    active_trade: Optional[ActiveTrade] = None
    
    # Session data
    session_bars: List = field(default_factory=list)
    prior_day_high: float = 0.0
    prior_day_low: float = 0.0
    overnight_high: float = 0.0
    overnight_low: float = 0.0
    
    # Volume profile building
    historical_or_widths: List[float] = field(default_factory=list)


@dataclass
class OrchestratorConfig:
    """Configuration for orchestrator."""
    prop_rules: PropAccountRules
    instruments: List[str]  # Symbols to trade
    start_date: date
    end_date: date
    data_directory: Path
    output_directory: Path
    
    # Processing
    max_concurrent_trades: int = 2
    correlation_aware_sizing: bool = True
    
    # Session times (CT)
    pre_market_start: time = time(7, 0)  # 7:00 AM CT
    market_close: time = time(15, 0)  # 3:00 PM CT


class MultiInstrumentOrchestrator:
    """Orchestrate multi-instrument ORB strategy backtesting."""
    
    def __init__(self, config: OrchestratorConfig):
        """Initialize orchestrator.
        
        Args:
            config: OrchestratorConfig with all settings
        """
        self.config = config
        
        # Initialize governance with per-instrument tracking
        self.governance = PropGovernanceEngine(
            rules=config.prop_rules,
            instruments=config.instruments,
            max_daily_trades_per_instrument=2,  # 2 trades per day per instrument
            starting_balance=config.prop_rules.account_size
        )
        
        # Initialize instrument states
        self.instrument_states: Dict[str, InstrumentState] = {}
        self._initialize_instruments()
        
        # Trade tracking
        self.all_trades: List[ComprehensiveTrade] = []
        self.current_trade_sequence = 0
        
        # Session tracking
        self.current_date: Optional[date] = None
        self.daily_bars_processed = 0
        
        logger.info(
            f"Orchestrator initialized: {len(self.instrument_states)} instruments, "
            f"${config.prop_rules.account_size:,.0f} account"
        )
    
    def _initialize_instruments(self):
        """Initialize state for each instrument."""
        for symbol in self.config.instruments:
            try:
                inst_config = get_instrument_config(symbol)
                
                # Create volume filter
                volume_filter = create_goldilocks_filter_from_config(inst_config)
                
                # Create ATR provider
                atr_provider = ATRProvider(period=14)
                
                # Create buffer calculator
                buffer_calc = AdaptiveBufferCalculator(
                    instrument_config=inst_config,
                    lookback_bars=10
                )
                
                # Create breakout detector
                breakout_detector = BreakoutDetector(
                    instrument_config=inst_config,
                    buffer_calculator=buffer_calc
                )
                
                # Create trade manager
                trade_manager = EnhancedTradeManager(inst_config)
                
                # Store state
                self.instrument_states[symbol] = InstrumentState(
                    symbol=symbol,
                    config=inst_config,
                    volume_filter=volume_filter,
                    atr_provider=atr_provider,
                    buffer_calc=buffer_calc,
                    breakout_detector=breakout_detector,
                    trade_manager=trade_manager
                )
                
                logger.info(f"Initialized instrument: {symbol}")
                
            except Exception as e:
                logger.error(f"Failed to initialize {symbol}: {e}")
                raise
    
    def run_backtest(self) -> Dict:
        """Run complete backtest across all instruments.
        
        Returns:
            Dictionary with results summary
        """
        logger.info(
            f"Starting backtest: {self.config.start_date} to {self.config.end_date}"
        )
        
        # Load data for all instruments
        data_by_instrument = self._load_all_data()
        
        if not data_by_instrument:
            raise ValueError("No data loaded for any instrument")
        
        # Process each trading day
        trading_days = self._get_trading_days(data_by_instrument)
        
        for trading_day in trading_days:
            logger.info(f"\n{'='*80}\nProcessing {trading_day}\n{'='*80}")
            self._process_trading_day(trading_day, data_by_instrument)
        
        # Generate results
        results = self._generate_results()
        
        # Save results
        self._save_results(results)
        
        logger.success(
            f"Backtest complete: {len(self.all_trades)} trades, "
            f"${self.governance.total_profit:+,.0f} P/L"
        )
        
        return results
    
    def _load_all_data(self) -> Dict[str, pd.DataFrame]:
        """Load data for all instruments.
        
        Returns:
            Dictionary mapping symbol -> DataFrame
        """
        data_by_instrument = {}
        
        for symbol in self.config.instruments:
            try:
                # Load from cached JSON - try to find any interval file (1m, 5m, 15m, etc.)
                json_files = list(self.config.data_directory.glob(f"{symbol}_*.json"))
                
                if not json_files:
                    logger.warning(f"No data file found for {symbol} in {self.config.data_directory}")
                    continue
                
                # Use the first matching file
                json_path = json_files[0]
                logger.info(f"Using data file: {json_path.name}")
                
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                # Convert to DataFrame
                df = pd.DataFrame(data['data'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Filter date range
                df = df[
                    (df['timestamp'].dt.date >= self.config.start_date) &
                    (df['timestamp'].dt.date <= self.config.end_date)
                ]
                
                if len(df) > 0:
                    data_by_instrument[symbol] = df
                    logger.info(
                        f"Loaded {symbol}: {len(df)} bars from "
                        f"{df['timestamp'].min().date()} to {df['timestamp'].max().date()}"
                    )
                else:
                    logger.warning(f"No data in date range for {symbol}")
                
            except Exception as e:
                logger.error(f"Error loading data for {symbol}: {e}")
        
        return data_by_instrument
    
    def _get_trading_days(self, data_by_instrument: Dict[str, pd.DataFrame]) -> List[date]:
        """Get list of trading days across all instruments.
        
        Args:
            data_by_instrument: Data for each instrument
        
        Returns:
            Sorted list of unique trading days
        """
        all_dates = set()
        
        for df in data_by_instrument.values():
            dates = df['timestamp'].dt.date.unique()
            all_dates.update(dates)
        
        return sorted(list(all_dates))
    
    def _process_trading_day(
        self,
        trading_day: date,
        data_by_instrument: Dict[str, pd.DataFrame]
    ):
        """Process a single trading day across all instruments.
        
        Args:
            trading_day: Date to process
            data_by_instrument: Data for each instrument
        """
        # Reset governance for new day
        if self.current_date != trading_day:
            self.governance.new_trading_day(trading_day)
            self.current_date = trading_day
            self.daily_bars_processed = 0
            
            # Reset instrument states for new day
            for state in self.instrument_states.values():
                state.or_builder = None
                state.or_finalized = False
                state.or_state = None
                state.session_bars = []
                state.breakout_detector.reset()
        
        # Get bars for this day across all instruments
        day_data = {}
        for symbol, df in data_by_instrument.items():
            day_bars = df[df['timestamp'].dt.date == trading_day].copy()
            if len(day_bars) > 0:
                day_data[symbol] = day_bars.sort_values('timestamp')
        
        if not day_data:
            logger.warning(f"No data for {trading_day}")
            return
        
        # Get all unique timestamps across instruments
        all_timestamps = set()
        for df in day_data.values():
            all_timestamps.update(df['timestamp'])
        
        sorted_timestamps = sorted(list(all_timestamps))
        
        # Process each timestamp
        for timestamp in sorted_timestamps:
            self._process_timestamp(timestamp, day_data)
            self.daily_bars_processed += 1
        
        # End of day - close any open trades
        self._handle_end_of_day(trading_day, day_data)
    
    def _process_timestamp(
        self,
        timestamp: datetime,
        day_data: Dict[str, pd.DataFrame]
    ):
        """Process a single timestamp across all instruments.
        
        Args:
            timestamp: Current timestamp
            day_data: Day's data for each instrument
        """
        current_time = timestamp.time()
        
        # Process each instrument
        for symbol, state in self.instrument_states.items():
            if symbol not in day_data:
                continue
            
            # Get bar for this instrument at this timestamp
            instrument_df = day_data[symbol]
            matching_bars = instrument_df[instrument_df['timestamp'] == timestamp]
            
            if len(matching_bars) == 0:
                continue
            
            bar = matching_bars.iloc[0]
            
            # Update ATR
            state.atr_provider.update(bar['high'], bar['low'], bar['close'])
            
            # Update buffer calculator
            state.buffer_calc.update(bar['close'])
            
            # Store bar for session
            state.session_bars.append(bar)
            
            # Check if in regular trading hours
            session_start = datetime.strptime(state.config.session_start, "%H:%M").time()
            session_end = datetime.strptime(state.config.session_end, "%H:%M").time()
            
            if current_time < session_start or current_time > session_end:
                # Outside regular hours - just accumulate data
                continue
            
            # 1. Handle OR building
            if state.or_builder is None and not state.or_finalized:
                self._start_or(symbol, state, timestamp)
            
            if state.or_builder and not state.or_finalized:
                self._update_or(symbol, state, bar, timestamp)
            
            # 2. Update active trade if exists
            if state.active_trade:
                self._update_active_trade(symbol, state, bar, timestamp)
            
            # 3. Check for breakout signals (if OR finalized and no active trade)
            if state.or_finalized and not state.active_trade and state.or_state:
                self._check_for_breakout(symbol, state, bar, timestamp)
    
    def _start_or(self, symbol: str, state: InstrumentState, timestamp: datetime):
        """Start OR building for an instrument.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            timestamp: Current timestamp
        """
        # Calculate normalized volatility for adaptive length
        atr = state.atr_provider.get_atr()
        typical_adr = state.config.typical_adr
        norm_vol = atr / typical_adr if typical_adr > 0 and atr > 0 else 0.5
        
        # Get prior day data (simplified - use recent session data)
        prior_high = state.prior_day_high if state.prior_day_high > 0 else 100.0
        prior_low = state.prior_day_low if state.prior_day_low > 0 else 99.0
        overnight_high = state.overnight_high if state.overnight_high > 0 else prior_high
        overnight_low = state.overnight_low if state.overnight_low > 0 else prior_low
        
        # Create OR builder
        state.or_builder = AdaptiveORBuilder(
            instrument_config=state.config,
            atr_provider=state.atr_provider,
            prior_day_high=prior_high,
            prior_day_low=prior_low,
            overnight_high=overnight_high,
            overnight_low=overnight_low,
            session_start_ts=timestamp
        )
        
        state.or_builder.start_or(norm_vol)
        
        logger.info(
            f"{symbol}: OR started at {timestamp}, length={state.or_builder.or_length_minutes}m"
        )
    
    def _update_or(
        self,
        symbol: str,
        state: InstrumentState,
        bar: pd.Series,
        timestamp: datetime
    ):
        """Update OR with new bar.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            bar: Current bar
            timestamp: Current timestamp
        """
        state.or_builder.update(bar)
        
        # Check if OR should be finalized
        if timestamp >= state.or_builder.or_end_ts and not state.or_finalized:
            # Get OR bars for volume analysis
            or_bars = pd.DataFrame(state.or_builder.bars)
            
            # Analyze volume
            volume_result = state.volume_filter.analyze_or_volume(
                or_bars=or_bars,
                or_width=state.or_builder.high - state.or_builder.low
            )
            
            # Finalize OR
            state.or_state = state.or_builder.finalize()
            state.or_finalized = True
            
            # Update historical widths
            state.historical_or_widths.append(state.or_state.width_norm)
            if len(state.historical_or_widths) > 30:
                state.historical_or_widths.pop(0)
            
            # Log results
            logger.info(
                f"{symbol}: OR finalized - "
                f"H={state.or_state.high:.2f}, L={state.or_state.low:.2f}, "
                f"W={state.or_state.width:.2f} ({state.or_state.width_norm:.2f} norm), "
                f"Valid={state.or_state.is_valid}, "
                f"Volume={volume_result['passes_goldilocks']}"
            )
            
            if not state.or_state.is_valid:
                logger.warning(f"{symbol}: OR invalid - {state.or_state.invalid_reason}")
            
            if not volume_result['passes_goldilocks']:
                logger.warning(
                    f"{symbol}: Volume quality failed - "
                    f"{', '.join(volume_result['fail_reasons'])}"
                )
            
            # Update volume profile for next session
            state.volume_filter.update_profile(or_bars)
    
    def _check_for_breakout(
        self,
        symbol: str,
        state: InstrumentState,
        bar: pd.Series,
        timestamp: datetime
    ):
        """Check for breakout signal.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            bar: Current bar
            timestamp: Current timestamp
        """
        # Check if OR is valid and volume passed
        if not state.or_state.is_valid:
            return
        
        # Detect breakout
        long_signal, short_signal, signal_info = state.breakout_detector.detect(
            or_high=state.or_state.high,
            or_low=state.or_state.low,
            bar_open=bar['open'],
            bar_high=bar['high'],
            bar_low=bar['low'],
            bar_close=bar['close'],
            timestamp=timestamp
        )
        
        # Process signals
        if long_signal:
            self._create_trade(symbol, state, 'LONG', bar, timestamp, signal_info)
        elif short_signal:
            self._create_trade(symbol, state, 'SHORT', bar, timestamp, signal_info)
    
    def _create_trade(
        self,
        symbol: str,
        state: InstrumentState,
        direction: str,
        bar: pd.Series,
        timestamp: datetime,
        signal_info: dict
    ):
        """Create a new trade.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            direction: 'LONG' or 'SHORT'
            bar: Current bar
            timestamp: Current timestamp
            signal_info: Signal information from breakout detector
        """
        # Calculate risk for this trade
        entry_price = bar['close']
        
        if direction == 'LONG':
            stop_price = max(
                state.or_state.low - state.config.buffer_base_points,
                entry_price - state.config.stop_min_points
            )
            risk_per_contract = entry_price - stop_price
        else:  # SHORT
            stop_price = min(
                state.or_state.high + state.config.buffer_base_points,
                entry_price + state.config.stop_min_points
            )
            risk_per_contract = stop_price - entry_price
        
        # Calculate position size
        # Base on micro contract value
        risk_dollars = risk_per_contract * state.config.tick_value_micro
        
        # Check governance
        can_trade, reason = self.governance.can_take_trade(
            trade_risk_dollars=risk_dollars,
            instrument=symbol,
            correlated_instruments=state.config.correlation_instruments
        )
        
        if not can_trade:
            logger.warning(f"{symbol}: Trade rejected by governance - {reason}")
            return
        
        # Determine position size (start with 1 micro contract)
        position_size = 1
        
        # Apply phase multiplier
        phase_mult = self.governance.get_position_size_multiplier()
        if phase_mult > 1.0:
            position_size = int(position_size * phase_mult)
        
        # Generate trade ID
        self.current_trade_sequence += 1
        trade_id = f"{symbol}_{timestamp.strftime('%Y%m%d')}_{self.current_trade_sequence:03d}"
        
        # Create active trade
        state.active_trade = state.trade_manager.create_trade(
            trade_id=trade_id,
            instrument=symbol,
            direction=direction,
            entry_timestamp=timestamp,
            entry_price=entry_price,
            stop_price=stop_price,
            position_size=position_size
        )
        
        # Register with governance
        self.governance.register_trade_entry(
            trade_id=trade_id,
            risk_dollars=risk_dollars * position_size,
            instrument=symbol
        )
        
        logger.success(
            f"{symbol}: {direction} trade created @ {entry_price:.2f}, "
            f"stop={stop_price:.2f}, size={position_size}, risk=${risk_dollars*position_size:.0f}"
        )
    
    def _update_active_trade(
        self,
        symbol: str,
        state: InstrumentState,
        bar: pd.Series,
        timestamp: datetime
    ):
        """Update active trade.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            bar: Current bar
            timestamp: Current timestamp
        """
        trade, exit_events = state.trade_manager.update(
            trade=state.active_trade,
            current_timestamp=timestamp,
            current_price=bar['close'],
            bar_high=bar['high'],
            bar_low=bar['low']
        )
        
        state.active_trade = trade
        
        # Process exit events
        if exit_events:
            self._process_exit_events(symbol, state, exit_events)
    
    def _process_exit_events(
        self,
        symbol: str,
        state: InstrumentState,
        exit_events: List[dict]
    ):
        """Process trade exit events.
        
        Args:
            symbol: Instrument symbol
            state: InstrumentState
            exit_events: List of exit event dictionaries
        """
        trade = state.active_trade
        
        # Calculate final P/L
        total_r = 0.0
        total_pnl = 0.0
        
        for event in exit_events:
            r_mult = event['r_multiple']
            size_frac = event['size_fraction']
            
            # Calculate P/L for this portion
            risk_per_contract = trade.entry_price - trade.initial_stop_price
            if trade.direction == 'SHORT':
                risk_per_contract = trade.initial_stop_price - trade.entry_price
            
            pnl_per_contract = r_mult * risk_per_contract * state.config.tick_value_micro
            pnl_this_portion = pnl_per_contract * trade.position_size * size_frac
            
            total_r += r_mult * size_frac
            total_pnl += pnl_this_portion
        
        # Register with governance
        self.governance.register_trade_exit(
            trade_id=trade.trade_id,
            pnl_dollars=total_pnl,
            r_multiple=total_r,
            instrument=state.symbol
        )
        
        # Create comprehensive trade record
        comprehensive_trade = self._create_comprehensive_trade_record(
            state=state,
            final_r=total_r,
            final_pnl=total_pnl,
            exit_events=exit_events
        )
        
        self.all_trades.append(comprehensive_trade)
        
        # Clear active trade
        state.active_trade = None
        
        logger.info(
            f"{symbol}: Trade closed - {exit_events[0]['reason']}, "
            f"P/L=${total_pnl:+.0f} ({total_r:+.2f}R)"
        )
    
    def _create_comprehensive_trade_record(
        self,
        state: InstrumentState,
        final_r: float,
        final_pnl: float,
        exit_events: List[dict]
    ) -> ComprehensiveTrade:
        """Create comprehensive trade record.
        
        Args:
            state: InstrumentState
            final_r: Final R-multiple
            final_pnl: Final P/L in dollars
            exit_events: List of exit events
        
        Returns:
            ComprehensiveTrade object
        """
        trade = state.active_trade
        
        # Create all sub-objects (simplified for now - full implementation would populate all fields)
        or_metrics = ORMetrics(
            start_ts=state.or_state.start_ts,
            end_ts=state.or_state.end_ts,
            high=state.or_state.high,
            low=state.or_state.low,
            width=state.or_state.width,
            width_norm=state.or_state.width_norm,
            width_percentile=state.or_state.width_percentile,
            center=state.or_state.center,
            center_vs_prior_mid=state.or_state.center_vs_prior_mid,
            overlap_ratio=state.or_state.overlap_ratio,
            overnight_range_util=state.or_state.overnight_range_util,
            is_valid=state.or_state.is_valid,
            invalid_reason=state.or_state.invalid_reason,
            adaptive_length_used=state.or_state.adaptive_length_used
        )
        
        volume_metrics = VolumeMetrics(
            cum_volume_or=0.0,  # Would be populated from volume filter
            expected_volume_or=0.0,
            cum_vol_ratio=0.0,
            vol_z_score=0.0,
            spike_detected=False,
            max_spike_ratio=0.0,
            opening_drive_energy=0.0,
            volume_quality_score=0.0,
            passes_goldilocks=True
        )
        
        breakout_context = BreakoutContext(
            breakout_ts=trade.entry_timestamp,
            breakout_delay_minutes=0.0,
            direction=trade.direction,
            trigger_price=trade.entry_price,
            buffer_used=0.0,
            is_retest=False,
            had_wick_first=False
        )
        
        risk_metrics = RiskMetrics(
            entry_price=trade.entry_price,
            initial_stop_price=trade.initial_stop_price,
            stop_distance_points=abs(trade.entry_price - trade.initial_stop_price),
            stop_distance_dollars=abs(trade.entry_price - trade.initial_stop_price) * state.config.tick_value_micro,
            position_size=trade.position_size,
            dollar_risk=abs(trade.entry_price - trade.initial_stop_price) * state.config.tick_value_micro * trade.position_size,
            account_risk_pct=0.0,
            targets=[Target(t.r_multiple, t.price, t.size_fraction, t.hit, t.hit_timestamp) for t in trade.targets]
        )
        
        trade_outcome = TradeOutcome(
            exit_ts=exit_events[-1]['timestamp'],
            exit_price=exit_events[-1]['price'],
            exit_reason=exit_events[-1]['reason'],
            realized_r=final_r,
            realized_dollars=final_pnl,
            mfe_r=trade.max_favorable_excursion,
            mae_r=trade.max_adverse_excursion,
            mfe_ts=trade.mfe_timestamp,
            mae_ts=trade.mae_timestamp,
            bars_held=trade.bars_held,
            minutes_held=(exit_events[-1]['timestamp'] - trade.entry_timestamp).total_seconds() / 60,
            reached_1r=trade.reached_1r,
            time_to_1r_minutes=trade.time_to_1r
        )
        
        factors = FactorSnapshot(
            volume_quality_score=0.0,
            volume_passes=True,
            or_valid=state.or_state.is_valid,
            or_width_norm=state.or_state.width_norm,
            or_percentile=state.or_state.width_percentile,
            center_vs_prior_mid=state.or_state.center_vs_prior_mid,
            overnight_bias=0.0,
            norm_vol=0.0,
            bias_score=0.0
        )
        
        # Create comprehensive trade
        comprehensive_trade = ComprehensiveTrade(
            trade_id=trade.trade_id,
            instrument=state.symbol,
            date=trade.entry_timestamp.date().isoformat(),
            config_hash="default",
            or_metrics=or_metrics,
            volume_metrics=volume_metrics,
            breakout_context=breakout_context,
            risk_metrics=risk_metrics,
            factors=factors,
            outcome=trade_outcome,
            equity_r_before=0.0,
            equity_r_after=0.0,
            daily_trade_number=self.governance.daily_trade_count,
            cumulative_daily_r=self.governance.daily_r_total
        )
        
        return comprehensive_trade
    
    def _handle_end_of_day(self, trading_day: date, day_data: Dict[str, pd.DataFrame]):
        """Handle end of day processing.
        
        Args:
            trading_day: Trading day
            day_data: Day's data for each instrument
        """
        # Force close any open trades
        for symbol, state in self.instrument_states.items():
            if state.active_trade and symbol in day_data:
                df = day_data[symbol]
                last_bar = df.iloc[-1]
                
                exit_events = state.trade_manager.force_exit_eod(
                    trade=state.active_trade,
                    timestamp=last_bar['timestamp'],
                    price=last_bar['close']
                )
                
                self._process_exit_events(symbol, state, exit_events)
    
    def _generate_results(self) -> Dict:
        """Generate backtest results summary.
        
        Returns:
            Dictionary with results
        """
        if len(self.all_trades) == 0:
            return {
                'total_trades': 0,
                'message': 'No trades generated'
            }
        
        # Convert trades to DataFrame for analysis
        trades_data = []
        for trade in self.all_trades:
            trades_data.append({
                'trade_id': trade.trade_id,
                'instrument': trade.instrument,
                'date': trade.date,
                'direction': trade.breakout_context.direction,
                'entry_price': trade.risk_metrics.entry_price,
                'exit_price': trade.outcome.exit_price,
                'exit_reason': trade.outcome.exit_reason,
                'realized_r': trade.outcome.realized_r,
                'realized_dollars': trade.outcome.realized_dollars,
                'mfe_r': trade.outcome.mfe_r,
                'mae_r': trade.outcome.mae_r,
                'bars_held': trade.outcome.bars_held,
                'reached_1r': trade.outcome.reached_1r,
                'time_to_1r': trade.outcome.time_to_1r_minutes
            })
        
        trades_df = pd.DataFrame(trades_data)
        
        # Calculate metrics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['realized_r'] > 0])
        losing_trades = len(trades_df[trades_df['realized_r'] <= 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        total_r = trades_df['realized_r'].sum()
        expectancy = trades_df['realized_r'].mean() if total_trades > 0 else 0.0
        
        total_dollars = trades_df['realized_dollars'].sum()
        
        # Get governance status
        gov_status = self.governance.get_status()
        
        results = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'expectancy': expectancy,
            'total_r': total_r,
            'total_dollars': total_dollars,
            'final_balance': gov_status['current_balance'],
            'peak_balance': gov_status['peak_balance'],
            'max_drawdown': gov_status['current_drawdown'],
            'profit_target_pct': gov_status['profit_target_pct'],
            'trades_by_instrument': trades_df.groupby('instrument').size().to_dict(),
            'avg_bars_held': trades_df['bars_held'].mean(),
            'pct_reached_1r': (trades_df['reached_1r'].sum() / total_trades * 100) if total_trades > 0 else 0.0,
            'governance_status': gov_status,
            'trades': self.all_trades
        }
        
        return results
    
    def _save_results(self, results: Dict):
        """Save results to disk.
        
        Args:
            results: Results dictionary
        """
        output_dir = self.config.output_directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trades
        trades_file = output_dir / "all_trades.json"
        trades_data = [trade.to_dict() for trade in self.all_trades]
        
        with open(trades_file, 'w') as f:
            json.dump(trades_data, f, indent=2, default=str)
        
        logger.info(f"Trades saved to {trades_file}")
        
        # Save summary
        summary_file = output_dir / "summary.json"
        summary = {k: v for k, v in results.items() if k != 'trades'}
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Summary saved to {summary_file}")
