"""Performance metrics calculation.

Computes standard trading metrics from trade results.
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from ..strategy.trade_state import ActiveTrade


@dataclass
class PerformanceMetrics:
    """Performance metrics summary.
    
    Attributes:
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Win rate (0-1)
        total_r: Total R-multiple
        average_r: Average R per trade
        median_r: Median R per trade
        expectancy: Expected R per trade
        profit_factor: Ratio of gross profit to gross loss
        sharpe_ratio: Sharpe ratio (assumes R as returns)
        sortino_ratio: Sortino ratio (downside deviation)
        max_drawdown_r: Maximum drawdown in R
        max_drawdown_pct: Maximum drawdown as %
        avg_winner_r: Average winning trade R
        avg_loser_r: Average losing trade R
        largest_winner_r: Largest winning trade R
        largest_loser_r: Largest losing trade R
        consecutive_wins: Maximum consecutive wins
        consecutive_losses: Maximum consecutive losses
        avg_trade_duration_minutes: Average trade duration
    """
    
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    total_r: float
    average_r: float
    median_r: float
    expectancy: float
    profit_factor: float
    
    sharpe_ratio: float
    sortino_ratio: float
    
    max_drawdown_r: float
    max_drawdown_pct: float
    
    avg_winner_r: float
    avg_loser_r: float
    largest_winner_r: float
    largest_loser_r: float
    
    consecutive_wins: int
    consecutive_losses: int
    
    avg_trade_duration_minutes: Optional[float] = None


def compute_equity_curve(trades: List[ActiveTrade]) -> pd.DataFrame:
    """Compute equity curve from trades.
    
    Args:
        trades: List of completed trades.
        
    Returns:
        DataFrame with columns: trade_number, cumulative_r, drawdown_r, drawdown_pct.
        
    Examples:
        >>> trades = [trade1, trade2, trade3]
        >>> equity = compute_equity_curve(trades)
        >>> print(equity[['trade_number', 'cumulative_r']])
    """
    if not trades:
        return pd.DataFrame(columns=['trade_number', 'cumulative_r', 'drawdown_r', 'drawdown_pct'])
    
    records = []
    cumulative_r = 0.0
    
    for i, trade in enumerate(trades):
        cumulative_r += trade.realized_r if trade.realized_r else 0.0
        
        records.append({
            'trade_number': i + 1,
            'trade_id': trade.trade_id,
            'entry_timestamp': trade.entry_timestamp,
            'exit_timestamp': trade.exit_timestamp,
            'realized_r': trade.realized_r,
            'cumulative_r': cumulative_r,
        })
    
    df = pd.DataFrame(records)
    
    # Compute drawdowns
    df['running_max'] = df['cumulative_r'].cummax()
    df['drawdown_r'] = df['cumulative_r'] - df['running_max']
    
    # Drawdown as percentage (using R as base)
    df['drawdown_pct'] = (df['drawdown_r'] / (df['running_max'] + 1e-10)) * 100
    
    return df


def compute_drawdowns(equity_curve: pd.DataFrame) -> pd.DataFrame:
    """Compute detailed drawdown analysis.
    
    Args:
        equity_curve: Equity curve from compute_equity_curve.
        
    Returns:
        DataFrame with drawdown periods (start, end, depth, duration).
        
    Examples:
        >>> equity = compute_equity_curve(trades)
        >>> drawdowns = compute_drawdowns(equity)
        >>> print(f"Max DD: {drawdowns['depth_r'].min():.2f}R")
    """
    if equity_curve.empty:
        return pd.DataFrame(columns=['start_idx', 'end_idx', 'depth_r', 'depth_pct', 'duration_trades'])
    
    # Find drawdown periods (when cumulative_r < running_max)
    in_drawdown = equity_curve['drawdown_r'] < 0
    
    # Find transitions
    drawdown_starts = (~in_drawdown.shift(1, fill_value=False)) & in_drawdown
    drawdown_ends = in_drawdown & (~in_drawdown.shift(-1, fill_value=False))
    
    starts = equity_curve.index[drawdown_starts].tolist()
    ends = equity_curve.index[drawdown_ends].tolist()
    
    # Match starts and ends
    if not starts:
        return pd.DataFrame(columns=['start_idx', 'end_idx', 'depth_r', 'depth_pct', 'duration_trades'])
    
    # If still in drawdown, add current index as end
    if len(ends) < len(starts):
        ends.append(equity_curve.index[-1])
    
    drawdowns = []
    for start, end in zip(starts, ends):
        dd_section = equity_curve.loc[start:end]
        depth_r = dd_section['drawdown_r'].min()
        depth_pct = dd_section['drawdown_pct'].min()
        duration = end - start + 1
        
        drawdowns.append({
            'start_idx': start,
            'end_idx': end,
            'depth_r': depth_r,
            'depth_pct': depth_pct,
            'duration_trades': duration,
        })
    
    return pd.DataFrame(drawdowns)


def compute_metrics(trades: List[ActiveTrade]) -> PerformanceMetrics:
    """Compute comprehensive performance metrics.
    
    Args:
        trades: List of completed trades.
        
    Returns:
        PerformanceMetrics with all statistics.
        
    Examples:
        >>> metrics = compute_metrics(trades)
        >>> print(f"Win rate: {metrics.win_rate:.1%}")
        >>> print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
        >>> print(f"Max DD: {metrics.max_drawdown_r:.2f}R")
    """
    if not trades:
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_r=0.0,
            average_r=0.0,
            median_r=0.0,
            expectancy=0.0,
            profit_factor=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown_r=0.0,
            max_drawdown_pct=0.0,
            avg_winner_r=0.0,
            avg_loser_r=0.0,
            largest_winner_r=0.0,
            largest_loser_r=0.0,
            consecutive_wins=0,
            consecutive_losses=0,
        )
    
    # Extract R-multiples
    r_values = [t.realized_r for t in trades if t.realized_r is not None]
    
    if not r_values:
        r_values = [0.0]
    
    # Basic counts
    total_trades = len(r_values)
    winning_trades = sum(1 for r in r_values if r > 0)
    losing_trades = sum(1 for r in r_values if r < 0)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
    
    # R statistics
    total_r = sum(r_values)
    average_r = np.mean(r_values)
    median_r = np.median(r_values)
    
    # Expectancy (average R)
    expectancy = average_r
    
    # Profit factor
    gross_profit = sum(r for r in r_values if r > 0)
    gross_loss = abs(sum(r for r in r_values if r < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Sharpe ratio (treating R as returns)
    if len(r_values) > 1 and np.std(r_values) > 0:
        sharpe_ratio = average_r / np.std(r_values) * np.sqrt(252)  # Annualized
    else:
        sharpe_ratio = 0.0
    
    # Sortino ratio (downside deviation)
    downside_returns = [r for r in r_values if r < 0]
    if downside_returns and np.std(downside_returns) > 0:
        sortino_ratio = average_r / np.std(downside_returns) * np.sqrt(252)
    else:
        sortino_ratio = 0.0
    
    # Drawdown
    equity_curve = compute_equity_curve(trades)
    if not equity_curve.empty:
        max_drawdown_r = equity_curve['drawdown_r'].min()
        max_drawdown_pct = equity_curve['drawdown_pct'].min()
    else:
        max_drawdown_r = 0.0
        max_drawdown_pct = 0.0
    
    # Winners/losers
    winners = [r for r in r_values if r > 0]
    losers = [r for r in r_values if r < 0]
    
    avg_winner_r = np.mean(winners) if winners else 0.0
    avg_loser_r = np.mean(losers) if losers else 0.0
    largest_winner_r = max(winners) if winners else 0.0
    largest_loser_r = min(losers) if losers else 0.0
    
    # Consecutive wins/losses
    consecutive_wins = _max_consecutive(r_values, positive=True)
    consecutive_losses = _max_consecutive(r_values, positive=False)
    
    # Trade duration
    durations = []
    for trade in trades:
        if trade.entry_timestamp and trade.exit_timestamp:
            duration = (trade.exit_timestamp - trade.entry_timestamp).total_seconds() / 60
            durations.append(duration)
    
    avg_duration = np.mean(durations) if durations else None
    
    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        total_r=total_r,
        average_r=average_r,
        median_r=median_r,
        expectancy=expectancy,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown_r=max_drawdown_r,
        max_drawdown_pct=max_drawdown_pct,
        avg_winner_r=avg_winner_r,
        avg_loser_r=avg_loser_r,
        largest_winner_r=largest_winner_r,
        largest_loser_r=largest_loser_r,
        consecutive_wins=consecutive_wins,
        consecutive_losses=consecutive_losses,
        avg_trade_duration_minutes=avg_duration,
    )


def _max_consecutive(values: List[float], positive: bool = True) -> int:
    """Find maximum consecutive wins or losses.
    
    Args:
        values: List of R-multiples.
        positive: If True, count wins; if False, count losses.
        
    Returns:
        Maximum consecutive count.
    """
    if not values:
        return 0
    
    max_streak = 0
    current_streak = 0
    
    for value in values:
        if positive and value > 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        elif not positive and value < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    return max_streak