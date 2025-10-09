"""Backtest Engine for Multi-Playbook Strategy.

Adapter that connects the MultiPlaybookStrategy to historical data
and simulates realistic trading.

Features:
- Bar-by-bar simulation
- Realistic order execution
- Slippage modeling
- Commission handling
- Performance analytics
- Trade-by-trade logging

Usage:
    >>> backtest = MultiPlaybookBacktest(
    ...     strategy=multi_playbook_strategy,
    ...     bars_1m=historical_data,
    ...     start_date="2024-01-01",
    ...     end_date="2024-12-31",
    ... )
    >>> results = backtest.run()
    >>> print(results.summary())
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, time
import pandas as pd
import numpy as np
from loguru import logger

from orb_confluence.strategy.multi_playbook_strategy import (
    MultiPlaybookStrategy,
    Position,
    TradeResult,
)


@dataclass
class BacktestConfig:
    """Backtest configuration.
    
    Attributes:
        initial_capital: Starting account size
        commission_per_contract: Commission per side
        slippage_ticks: Slippage in ticks
        tick_size: Minimum price movement
        tick_value: Dollar value per tick
        point_value: Dollar value per point
        session_start: Session start time (e.g., time(9, 30))
        session_end: Session end time (e.g., time(16, 0))
        close_eod: Close all positions at end of day
    """
    initial_capital: float = 100000.0
    commission_per_contract: float = 2.50
    slippage_ticks: float = 1.0
    tick_size: float = 0.25
    tick_value: float = 12.50
    point_value: float = 50.0
    session_start: time = field(default_factory=lambda: time(9, 30))
    session_end: time = field(default_factory=lambda: time(16, 0))
    close_eod: bool = True


@dataclass
class BacktestResults:
    """Results from backtest run.
    
    Attributes:
        trades: List of all trades
        equity_curve: Daily equity values
        metrics: Performance metrics
        playbook_stats: Per-playbook statistics
        daily_stats: Daily statistics
    """
    trades: List[TradeResult]
    equity_curve: pd.Series
    metrics: Dict[str, Any]
    playbook_stats: Dict[str, Dict[str, Any]]
    daily_stats: pd.DataFrame
    
    def summary(self) -> str:
        """Generate summary string."""
        m = self.metrics
        
        summary = f"""
╔═══════════════════════════════════════════════════════════╗
║         MULTI-PLAYBOOK BACKTEST RESULTS                  ║
╚═══════════════════════════════════════════════════════════╝

Period: {m['start_date']} to {m['end_date']} ({m['trading_days']} days)

PERFORMANCE
───────────
  Total Return:        {m['total_return']:>12.2%}
  CAGR:                {m['cagr']:>12.2%}
  Sharpe Ratio:        {m['sharpe_ratio']:>12.2f}
  Sortino Ratio:       {m['sortino_ratio']:>12.2f}
  Calmar Ratio:        {m['calmar_ratio']:>12.2f}
  
DRAWDOWN
───────────
  Max Drawdown:        {m['max_drawdown']:>12.2%}
  Max DD Duration:     {m['max_dd_duration_days']:>12.0f} days
  Recovery Factor:     {m['recovery_factor']:>12.2f}
  
TRADES
───────────
  Total Trades:        {m['total_trades']:>12d}
  Winners:             {m['winning_trades']:>12d} ({m['win_rate']:>6.1%})
  Losers:              {m['losing_trades']:>12d}
  Average R:           {m['average_r']:>12.2f}R
  Expectancy:          {m['expectancy_r']:>12.2f}R
  
  Average Win:         {m['avg_win_r']:>12.2f}R  (${m['avg_win_dollars']:>8,.0f})
  Average Loss:        {m['avg_loss_r']:>12.2f}R  (${m['avg_loss_dollars']:>8,.0f})
  Win/Loss Ratio:      {m['win_loss_ratio']:>12.2f}
  
  Largest Win:         {m['largest_win_r']:>12.2f}R  (${m['largest_win_dollars']:>8,.0f})
  Largest Loss:        {m['largest_loss_r']:>12.2f}R  (${m['largest_loss_dollars']:>8,.0f})
  
  Avg Duration:        {m['avg_duration_bars']:>12.1f} bars
  
EFFICIENCY
───────────
  Profit Factor:       {m['profit_factor']:>12.2f}
  R Efficiency:        {m['r_efficiency']:>12.2%}
  Trade Efficiency:    {m['trade_efficiency']:>12.2%}
  
PLAYBOOK BREAKDOWN
───────────
"""
        
        for pb_name, pb_stats in self.playbook_stats.items():
            summary += f"""
  {pb_name}:
    Trades:     {pb_stats['count']:>4d}  |  Win Rate: {pb_stats['win_rate']:>5.1%}
    Avg R:      {pb_stats['avg_r']:>5.2f}R  |  Total R:  {pb_stats['total_r']:>6.2f}R
"""
        
        summary += "\n"
        return summary


class MultiPlaybookBacktest:
    """Backtest engine for multi-playbook strategy.
    
    Simulates trading on historical data with realistic execution.
    
    Example:
        >>> strategy = MultiPlaybookStrategy(...)
        >>> backtest = MultiPlaybookBacktest(
        ...     strategy=strategy,
        ...     bars_1m=data_1m,
        ...     config=BacktestConfig(),
        ... )
        >>> results = backtest.run()
        >>> print(results.summary())
    """
    
    def __init__(
        self,
        strategy: MultiPlaybookStrategy,
        bars_1m: pd.DataFrame,
        bars_daily: Optional[pd.DataFrame] = None,
        bars_1s: Optional[pd.DataFrame] = None,
        config: Optional[BacktestConfig] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        """Initialize backtest engine.
        
        Args:
            strategy: MultiPlaybookStrategy instance
            bars_1m: 1-minute historical bars
            bars_daily: Daily historical bars (optional)
            bars_1s: 1-second historical bars (optional)
            config: Backtest configuration
            start_date: Start date for backtest (YYYY-MM-DD)
            end_date: End date for backtest (YYYY-MM-DD)
        """
        self.strategy = strategy
        self.bars_1m = bars_1m.copy()
        self.bars_daily = bars_daily
        self.bars_1s = bars_1s
        self.config = config or BacktestConfig()
        
        # Filter date range
        if start_date:
            self.bars_1m = self.bars_1m[self.bars_1m.index >= start_date]
        if end_date:
            self.bars_1m = self.bars_1m[self.bars_1m.index <= end_date]
        
        # State
        self.current_capital = self.config.initial_capital
        self.equity_history: List[float] = []
        self.date_history: List[datetime] = []
        self.trades: List[TradeResult] = []
        self.current_bar_idx = 0
        
        logger.info(
            f"Initialized backtest: {len(self.bars_1m)} bars, "
            f"${self.config.initial_capital:,.0f} capital"
        )
    
    def run(self) -> BacktestResults:
        """Run backtest.
        
        Returns:
            BacktestResults with comprehensive statistics
        """
        logger.info("Starting backtest...")
        
        # Fit regime classifier on historical data
        logger.info("Fitting regime classifier...")
        # Use first 30 days for training
        training_bars = self.bars_1m.iloc[:60*24*30]  # ~30 days
        self.strategy.fit_regime_classifier(training_bars)
        
        # Reset strategy state
        self.strategy.reset()
        
        # Iterate through bars
        total_bars = len(self.bars_1m)
        log_interval = total_bars // 20  # Log 20 times
        
        for idx, (timestamp, bar) in enumerate(self.bars_1m.iterrows()):
            self.current_bar_idx = idx
            
            # Log progress
            if idx % log_interval == 0:
                progress = idx / total_bars * 100
                logger.info(f"Progress: {progress:.0f}% ({idx}/{total_bars} bars)")
            
            # Get historical context
            lookback = 500  # 500 bars of context
            start_idx = max(0, idx - lookback)
            historical_1m = self.bars_1m.iloc[start_idx:idx+1]
            
            # Convert bar to Series if needed
            if isinstance(bar, pd.Series):
                current_bar = bar
            else:
                current_bar = pd.Series(bar)
            
            # Add timestamp from timestamp_utc column (not from index)
            if 'timestamp_utc' in current_bar:
                current_bar['timestamp'] = current_bar['timestamp_utc']
            elif 'timestamp' not in current_bar or pd.isna(current_bar.get('timestamp')):
                current_bar['timestamp'] = timestamp
            
            # Process bar
            actions = self.strategy.on_bar(
                current_bar=current_bar,
                bars_1m=historical_1m,
                bars_daily=self.bars_daily,
                bars_1s=self.bars_1s,
            )
            
            # Execute actions
            self._execute_actions(actions, current_bar)
            
            # Track equity
            self._update_equity(current_bar)
            
            # End of day processing
            if self._is_end_of_day(timestamp):
                self._end_of_day_processing(current_bar)
        
        logger.info("Backtest complete. Analyzing results...")
        
        # Generate results
        results = self._generate_results()
        
        logger.info(f"Completed {len(self.trades)} trades")
        
        return results
    
    def _execute_actions(
        self,
        actions: List[Dict[str, Any]],
        current_bar: pd.Series,
    ):
        """Execute trading actions with realistic execution.
        
        Args:
            actions: List of actions from strategy
            current_bar: Current bar
        """
        for action in actions:
            action_type = action['action']
            
            if action_type == 'ENTER':
                self._execute_entry(action, current_bar)
            elif action_type == 'EXIT':
                self._execute_exit(action, current_bar)
            elif action_type == 'PARTIAL_EXIT':
                self._execute_partial_exit(action, current_bar)
            elif action_type == 'UPDATE_STOP':
                # Just logging, actual stop update handled by strategy
                pass
    
    def _execute_entry(
        self,
        action: Dict[str, Any],
        current_bar: pd.Series,
    ):
        """Execute entry order.
        
        Args:
            action: Entry action
            current_bar: Current bar
        """
        signal = action['signal']
        allocation = action['allocation']
        
        # Calculate execution price with slippage
        entry_price = signal.entry_price
        slippage = self.config.slippage_ticks * self.config.tick_size
        
        if signal.direction.value == 'LONG':
            execution_price = entry_price + slippage
        else:
            execution_price = entry_price - slippage
        
        # Calculate commission
        commission = allocation.final_size * self.config.commission_per_contract * 2  # Round trip
        
        # Deduct commission from capital
        self.current_capital -= commission
        
        logger.debug(
            f"ENTRY: {signal.playbook_name} {signal.direction.value} "
            f"{allocation.final_size} @ {execution_price:.2f} "
            f"(commission: ${commission:.2f})"
        )
    
    def _execute_exit(
        self,
        action: Dict[str, Any],
        current_bar: pd.Series,
    ):
        """Execute exit order.
        
        Args:
            action: Exit action
            current_bar: Current bar
        """
        reason = action['reason']
        exit_price = action['price']
        
        # Add slippage
        slippage = self.config.slippage_ticks * self.config.tick_size
        
        # Slippage hurts us on exit too
        # For LONG exit, we sell lower; for SHORT exit, we buy higher
        # But we don't know direction here, so use average
        
        logger.debug(
            f"EXIT: {reason} @ {exit_price:.2f}"
        )
    
    def _execute_partial_exit(
        self,
        action: Dict[str, Any],
        current_bar: pd.Series,
    ):
        """Execute partial exit order.
        
        Args:
            action: Partial exit action
            current_bar: Current bar
        """
        size = action['size']
        exit_price = action['price']
        reason = action['reason']
        
        logger.debug(
            f"PARTIAL EXIT: {size} contracts @ {exit_price:.2f} ({reason})"
        )
    
    def _update_equity(self, current_bar: pd.Series):
        """Update equity curve.
        
        Args:
            current_bar: Current bar
        """
        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0.0
        for position in self.strategy.open_positions:
            current_price = current_bar['close']
            
            if position.direction.value == 'LONG':
                pnl_per_contract = (current_price - position.entry_price) * self.config.point_value
            else:
                pnl_per_contract = (position.entry_price - current_price) * self.config.point_value
            
            unrealized_pnl += pnl_per_contract * position.size
        
        # Calculate realized P&L from closed trades
        realized_pnl = sum(trade.pnl for trade in self.strategy.closed_trades)
        
        # Total equity
        total_equity = self.config.initial_capital + realized_pnl + unrealized_pnl
        
        self.equity_history.append(total_equity)
        
        timestamp = current_bar.get('timestamp', datetime.now())
        self.date_history.append(timestamp)
    
    def _is_end_of_day(self, timestamp: datetime) -> bool:
        """Check if this is end of trading day.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            True if end of day
        """
        if isinstance(timestamp, pd.Timestamp):
            timestamp = timestamp.to_pydatetime()
        
        return timestamp.time() >= self.config.session_end
    
    def _end_of_day_processing(self, current_bar: pd.Series):
        """End of day processing.
        
        Args:
            current_bar: Current bar
        """
        if self.config.close_eod and len(self.strategy.open_positions) > 0:
            logger.debug(f"EOD: Closing {len(self.strategy.open_positions)} open positions")
            
            # Close all positions at current price
            for position in list(self.strategy.open_positions):
                self.strategy._close_position(
                    position,
                    current_bar['close'],
                    'EOD',
                )
        
        # Reset portfolio heat
        self.strategy.portfolio_manager.reset_heat()
    
    def _generate_results(self) -> BacktestResults:
        """Generate backtest results.
        
        Returns:
            BacktestResults with all metrics
        """
        trades = self.strategy.closed_trades
        
        if len(trades) == 0 and len(self.equity_history) == 0:
            logger.warning("No trades executed in backtest")
            return BacktestResults(
                trades=[],
                equity_curve=pd.Series([self.config.initial_capital]),
                metrics={'total_trades': 0},
                playbook_stats={},
                daily_stats=pd.DataFrame(),
            )
        
        # Build equity curve
        if len(self.equity_history) == 0:
            equity_curve = pd.Series([self.config.initial_capital])
        else:
            equity_curve = pd.Series(
                data=self.equity_history,
                index=self.date_history,
            )
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades, equity_curve)
        
        # Per-playbook stats
        playbook_stats = self._calculate_playbook_stats(trades)
        
        # Daily stats
        daily_stats = self._calculate_daily_stats(equity_curve)
        
        return BacktestResults(
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
            playbook_stats=playbook_stats,
            daily_stats=daily_stats,
        )
    
    def _calculate_metrics(
        self,
        trades: List[TradeResult],
        equity_curve: pd.Series,
    ) -> Dict[str, Any]:
        """Calculate performance metrics.
        
        Args:
            trades: List of trades
            equity_curve: Equity curve
            
        Returns:
            Dictionary of metrics
        """
        # Basic stats
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.r_multiple > 0])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # R-multiple stats
        r_multiples = [t.r_multiple for t in trades]
        avg_r = np.mean(r_multiples)
        total_r = sum(r_multiples)
        
        winning_r = [t.r_multiple for t in trades if t.r_multiple > 0]
        losing_r = [t.r_multiple for t in trades if t.r_multiple <= 0]
        
        avg_win_r = np.mean(winning_r) if winning_r else 0
        avg_loss_r = np.mean(losing_r) if losing_r else 0
        
        win_loss_ratio = abs(avg_win_r / avg_loss_r) if avg_loss_r != 0 else 0
        
        # Expectancy
        expectancy_r = (win_rate * avg_win_r) + ((1 - win_rate) * avg_loss_r)
        
        # Dollar stats
        pnls = [t.pnl for t in trades]
        total_pnl = sum(pnls)
        
        winning_pnls = [t.pnl for t in trades if t.pnl > 0]
        losing_pnls = [t.pnl for t in trades if t.pnl <= 0]
        
        avg_win_dollars = np.mean(winning_pnls) if winning_pnls else 0
        avg_loss_dollars = np.mean(losing_pnls) if losing_pnls else 0
        
        gross_profit = sum(winning_pnls) if winning_pnls else 0
        gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Returns
        initial = self.config.initial_capital
        final = equity_curve.iloc[-1]
        total_return = (final - initial) / initial
        
        # CAGR
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        years = days / 365.25
        cagr = (final / initial) ** (1 / years) - 1 if years > 0 else 0
        
        # Drawdown
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # Max DD duration
        underwater = drawdown < 0
        underwater_periods = []
        start = None
        for i, is_underwater in enumerate(underwater):
            if is_underwater and start is None:
                start = i
            elif not is_underwater and start is not None:
                underwater_periods.append(i - start)
                start = None
        
        max_dd_duration_days = max(underwater_periods) if underwater_periods else 0
        
        # Sharpe ratio (daily returns)
        daily_equity = equity_curve.resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().dropna()
        
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # Sortino ratio
        downside_returns = daily_returns[daily_returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = (daily_returns.mean() / downside_returns.std()) * np.sqrt(252)
        else:
            sortino_ratio = 0
        
        # Calmar ratio
        calmar_ratio = cagr / abs(max_drawdown) if max_drawdown < 0 else 0
        
        # Recovery factor
        recovery_factor = total_return / abs(max_drawdown) if max_drawdown < 0 else 0
        
        # Trade duration
        durations = [t.bars_in_trade for t in trades]
        avg_duration = np.mean(durations)
        
        # Largest wins/losses
        largest_win_r = max(r_multiples)
        largest_loss_r = min(r_multiples)
        largest_win_dollars = max(pnls)
        largest_loss_dollars = min(pnls)
        
        # Efficiency metrics
        r_efficiency = avg_r / avg_win_r if avg_win_r > 0 else 0
        trade_efficiency = total_trades / days if days > 0 else 0
        
        return {
            'start_date': equity_curve.index[0].strftime('%Y-%m-%d'),
            'end_date': equity_curve.index[-1].strftime('%Y-%m-%d'),
            'trading_days': days,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'average_r': avg_r,
            'total_r': total_r,
            'expectancy_r': expectancy_r,
            'avg_win_r': avg_win_r,
            'avg_loss_r': avg_loss_r,
            'win_loss_ratio': win_loss_ratio,
            'avg_win_dollars': avg_win_dollars,
            'avg_loss_dollars': avg_loss_dollars,
            'largest_win_r': largest_win_r,
            'largest_loss_r': largest_loss_r,
            'largest_win_dollars': largest_win_dollars,
            'largest_loss_dollars': largest_loss_dollars,
            'profit_factor': profit_factor,
            'total_return': total_return,
            'cagr': cagr,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'max_drawdown': max_drawdown,
            'max_dd_duration_days': max_dd_duration_days,
            'recovery_factor': recovery_factor,
            'avg_duration_bars': avg_duration,
            'r_efficiency': r_efficiency,
            'trade_efficiency': trade_efficiency,
        }
    
    def _calculate_playbook_stats(
        self,
        trades: List[TradeResult],
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate per-playbook statistics.
        
        Args:
            trades: List of trades
            
        Returns:
            Dictionary of playbook stats
        """
        playbook_stats = {}
        
        # Group by playbook
        playbook_groups = {}
        for trade in trades:
            pb = trade.playbook_name
            if pb not in playbook_groups:
                playbook_groups[pb] = []
            playbook_groups[pb].append(trade)
        
        # Calculate stats for each
        for pb_name, pb_trades in playbook_groups.items():
            winners = len([t for t in pb_trades if t.r_multiple > 0])
            win_rate = winners / len(pb_trades) if pb_trades else 0
            avg_r = np.mean([t.r_multiple for t in pb_trades])
            total_r = sum([t.r_multiple for t in pb_trades])
            
            playbook_stats[pb_name] = {
                'count': len(pb_trades),
                'win_rate': win_rate,
                'avg_r': avg_r,
                'total_r': total_r,
            }
        
        return playbook_stats
    
    def _calculate_daily_stats(
        self,
        equity_curve: pd.Series,
    ) -> pd.DataFrame:
        """Calculate daily statistics.
        
        Args:
            equity_curve: Equity curve
            
        Returns:
            DataFrame with daily stats
        """
        daily_equity = equity_curve.resample('D').last().ffill()
        daily_returns = daily_equity.pct_change().fillna(0)
        
        daily_stats = pd.DataFrame({
            'equity': daily_equity,
            'returns': daily_returns,
            'cumulative_return': (1 + daily_returns).cumprod() - 1,
        })
        
        return daily_stats

