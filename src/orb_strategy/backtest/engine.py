"""Event-driven backtest engine.

Processes bar data sequentially, building ORs, detecting signals, managing trades,
and enforcing governance.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from loguru import logger

from ..config import StrategyConfig, InstrumentConfig
from ..data import DataManager
from ..features import ORBuilder, OpeningRange
from ..signals import ConfluenceScorer, BreakoutDetector
from ..execution import TradeManager, Position
from ..governance import GovernanceController


@dataclass
class BacktestResult:
    """Backtest results container."""

    run_id: str
    config: StrategyConfig
    
    # Data
    trades: List[Position] = field(default_factory=list)
    opening_ranges: List[OpeningRange] = field(default_factory=list)
    
    # Performance metrics (computed post-run)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    avg_r: float = 0.0
    total_r: float = 0.0
    max_r: float = 0.0
    min_r: float = 0.0
    
    expectancy: float = 0.0
    profit_factor: float = 0.0
    
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    # Equity curve (R-based)
    equity_curve: Optional[pd.DataFrame] = None
    
    # Diagnostics
    or_valid_count: int = 0
    or_invalid_count: int = 0
    signals_blocked_by_governance: int = 0
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class BacktestEngine:
    """Event-driven backtest engine.

    Simulates sequential bar-by-bar execution with OR building, signal detection,
    trade management, and governance enforcement.
    """

    def __init__(
        self,
        config: StrategyConfig,
        data_manager: DataManager,
    ) -> None:
        """Initialize backtest engine.

        Args:
            config: Strategy configuration.
            data_manager: Data manager for fetching bars.
        """
        self.config = config
        self.data_manager = data_manager

        # Set random seed for determinism
        np.random.seed(config.backtest.random_seed)

    def run(self) -> BacktestResult:
        """Run backtest across all enabled instruments.

        Returns:
            BacktestResult with trades and metrics.
        """
        run_id = str(uuid4())[:8]
        logger.info(f"Starting backtest run {run_id}")

        result = BacktestResult(
            run_id=run_id,
            config=self.config,
            start_time=datetime.utcnow(),
        )

        # Run for each enabled instrument
        for symbol, instrument in self.config.instruments.items():
            if not instrument.enabled:
                logger.info(f"Skipping disabled instrument: {symbol}")
                continue

            logger.info(f"Running backtest for {symbol}")
            
            try:
                instrument_result = self._run_instrument(instrument)
                
                # Aggregate results
                result.trades.extend(instrument_result["trades"])
                result.opening_ranges.extend(instrument_result["opening_ranges"])
                result.signals_blocked_by_governance += instrument_result["signals_blocked"]
                
            except Exception as e:
                logger.error(f"Backtest failed for {symbol}: {e}", exc_info=True)
                continue

        result.end_time = datetime.utcnow()

        # Compute metrics
        self._compute_metrics(result)

        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"win rate: {result.win_rate:.1%}, "
            f"avg R: {result.avg_r:.2f}, "
            f"total R: {result.total_r:.2f}"
        )

        return result

    def _run_instrument(self, instrument: InstrumentConfig) -> Dict:
        """Run backtest for a single instrument.

        Args:
            instrument: Instrument configuration.

        Returns:
            Dict with trades, ORs, and diagnostics.
        """
        # Fetch data
        start = pd.Timestamp(self.config.backtest.start_date, tz="UTC")
        end = pd.Timestamp(self.config.backtest.end_date, tz="UTC")

        df = self.data_manager.fetch_data(
            instrument=instrument,
            start=start,
            end=end,
            interval="1m",
        )

        if df.empty:
            logger.warning(f"No data available for {instrument.symbol}")
            return {
                "trades": [],
                "opening_ranges": [],
                "signals_blocked": 0,
            }

        logger.info(f"Loaded {len(df)} bars for {instrument.symbol}")

        # Initialize components
        or_builder = ORBuilder(self.config.orb, instrument)
        confluence_scorer = ConfluenceScorer(self.config.scoring, self.config.factors)
        breakout_detector = BreakoutDetector(
            self.config.orb,
            self.config.buffers,
            confluence_scorer,
        )
        trade_manager = TradeManager(self.config.trade, self.config.orb)
        governance = GovernanceController(self.config.governance)

        # Build all opening ranges
        opening_ranges = or_builder.build_opening_ranges(df)
        logger.info(f"Built {len(opening_ranges)} opening ranges")

        # Map dates to ORs
        or_map: Dict[datetime.date, OpeningRange] = {
            or_obj.date.date(): or_obj for or_obj in opening_ranges
        }

        # State
        open_positions: List[Position] = []
        closed_positions: List[Position] = []
        signals_blocked = 0
        current_date: Optional[datetime.date] = None

        # Sequential bar processing
        for bar_idx in range(len(df)):
            bar_time = df.index[bar_idx]
            bar_date = bar_time.date()

            # Day transition
            if current_date is None or bar_date != current_date:
                current_date = bar_date
                governance.reset_for_new_day(current_date)

                logger.debug(f"Processing day: {current_date}")

            # Get OR for this day
            opening_range = or_map.get(bar_date)

            if opening_range is None:
                continue

            # Update open positions
            for position in open_positions:
                trade_manager.update_position(position, df, bar_idx)

                # If position closed, move to closed list
                if position.is_closed:
                    closed_positions.append(position)
                    governance.record_position_closed(position)

            # Remove closed positions
            open_positions = [p for p in open_positions if p.is_open]

            # Check for new signals (only if no open position for this instrument)
            if not open_positions:  # Simplified: one position at a time
                # Check governance
                can_take, block_reason = governance.can_take_signal(
                    instrument.symbol,
                    bar_time,
                )

                if not can_take:
                    signals_blocked += 1
                    continue

                # Detect breakout
                signal = breakout_detector.detect_breakout(
                    df=df,
                    bar_idx=bar_idx,
                    opening_range=opening_range,
                )

                if signal is not None:
                    # Record signal and create position
                    governance.record_signal(instrument.symbol, bar_time)
                    
                    position = trade_manager.create_position(signal, opening_range)
                    open_positions.append(position)
                    governance.record_position_opened(position)

                    logger.info(
                        f"Opened {position.direction.value} position for {instrument.symbol} "
                        f"at {position.entry_price}"
                    )

        # Close any remaining open positions (end of backtest)
        for position in open_positions:
            if position.is_open:
                final_bar = df.iloc[-1]
                position.close_position(
                    exit_time=df.index[-1],
                    exit_price=final_bar["close"],
                    exit_reason=ExitReason.SESSION_END,
                )
                closed_positions.append(position)

        return {
            "trades": closed_positions,
            "opening_ranges": opening_ranges,
            "signals_blocked": signals_blocked,
        }

    def _compute_metrics(self, result: BacktestResult) -> None:
        """Compute performance metrics from trades.

        Args:
            result: BacktestResult to populate.
        """
        trades = result.trades
        result.total_trades = len(trades)

        if result.total_trades == 0:
            return

        # Extract R values
        r_values = [t.realized_r for t in trades]

        result.winning_trades = sum(1 for r in r_values if r > 0)
        result.losing_trades = sum(1 for r in r_values if r <= 0)
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0.0

        result.avg_r = np.mean(r_values)
        result.total_r = np.sum(r_values)
        result.max_r = np.max(r_values)
        result.min_r = np.min(r_values)

        # Expectancy
        if result.total_trades > 0:
            wins = [r for r in r_values if r > 0]
            losses = [abs(r) for r in r_values if r <= 0]
            
            avg_win = np.mean(wins) if wins else 0.0
            avg_loss = np.mean(losses) if losses else 0.0
            
            result.expectancy = (
                result.win_rate * avg_win - (1 - result.win_rate) * avg_loss
            )

        # Profit factor
        gross_profit = sum(r for r in r_values if r > 0)
        gross_loss = abs(sum(r for r in r_values if r <= 0))

        if gross_loss > 0:
            result.profit_factor = gross_profit / gross_loss
        else:
            result.profit_factor = float("inf") if gross_profit > 0 else 0.0

        # Consecutive streaks
        result.max_consecutive_wins = self._max_streak(r_values, positive=True)
        result.max_consecutive_losses = self._max_streak(r_values, positive=False)

        # OR statistics
        result.or_valid_count = sum(1 for or_obj in result.opening_ranges if or_obj.is_valid)
        result.or_invalid_count = len(result.opening_ranges) - result.or_valid_count

        # Build equity curve
        result.equity_curve = self._build_equity_curve(trades)

    @staticmethod
    def _max_streak(r_values: List[float], positive: bool) -> int:
        """Calculate maximum consecutive wins or losses.

        Args:
            r_values: List of R values.
            positive: True for wins, False for losses.

        Returns:
            Maximum streak length.
        """
        max_streak = 0
        current_streak = 0

        for r in r_values:
            if (positive and r > 0) or (not positive and r <= 0):
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        return max_streak

    @staticmethod
    def _build_equity_curve(trades: List[Position]) -> pd.DataFrame:
        """Build R-based equity curve.

        Args:
            trades: List of closed positions.

        Returns:
            DataFrame with cumulative R over time.
        """
        if not trades:
            return pd.DataFrame(columns=["timestamp", "cumulative_r"])

        equity_data = []
        cumulative_r = 0.0

        for trade in sorted(trades, key=lambda t: t.entry_time):
            if trade.final_exit_time is None:
                continue

            cumulative_r += trade.realized_r

            equity_data.append({
                "timestamp": trade.final_exit_time,
                "cumulative_r": cumulative_r,
                "trade_id": trade.trade_id,
                "r": trade.realized_r,
            })

        df = pd.DataFrame(equity_data)
        df = df.set_index("timestamp").sort_index()

        return df


# Missing import
from ..execution.position import ExitReason
