#!/usr/bin/env python3
"""Generate realistic trades with full OHLCV bar data for visualization.

This script creates a complete backtest result with:
- Realistic OHLCV minute bars
- Trade entries/exits aligned to bars
- OR high/low zones
- Stop loss and take profit levels
- Full metadata for visualization
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json


def generate_realistic_bars(start_time: datetime, duration_minutes: int, 
                           base_price: float, volatility: float = 0.002) -> pd.DataFrame:
    """Generate realistic OHLCV minute bars.
    
    Args:
        start_time: Starting timestamp
        duration_minutes: Number of minutes to generate
        base_price: Starting price
        volatility: Price volatility per bar
        
    Returns:
        DataFrame with OHLCV data
    """
    timestamps = [start_time + timedelta(minutes=i) for i in range(duration_minutes)]
    bars = []
    
    current_price = base_price
    
    for ts in timestamps:
        # Random walk with trend
        drift = np.random.randn() * volatility * base_price
        current_price += drift
        
        # Generate OHLC from close
        spread = abs(np.random.randn()) * volatility * base_price
        high = current_price + spread
        low = current_price - spread
        open_price = np.random.uniform(low, high)
        close = current_price
        
        # Ensure OHLC validity
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        # Volume with some variance
        volume = int(np.random.lognormal(14, 0.5))  # ~1M average
        
        bars.append({
            'timestamp': ts,
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': volume
        })
    
    return pd.DataFrame(bars)


def generate_or_zone(bars: pd.DataFrame, or_minutes: int = 15) -> tuple[float, float]:
    """Extract OR high/low from first N minutes.
    
    Args:
        bars: OHLCV data
        or_minutes: OR duration in minutes
        
    Returns:
        (or_high, or_low)
    """
    or_bars = bars.iloc[:or_minutes]
    or_high = or_bars['high'].max()
    or_low = or_bars['low'].min()
    return or_high, or_low


def create_trade_with_bars(trade_date: datetime, direction: str, base_price: float,
                          realized_r: float, trade_id: str) -> dict:
    """Create a complete trade with OHLCV bar data.
    
    Args:
        trade_date: Trade date
        direction: 'long' or 'short'
        base_price: Starting price for the day
        realized_r: R-multiple outcome
        trade_id: Unique trade identifier
        
    Returns:
        Dict with trade data and bars
    """
    # Generate full day of bars (390 minutes = 6.5 hours)
    day_start = trade_date.replace(hour=9, minute=30, second=0)
    bars = generate_realistic_bars(day_start, 390, base_price, volatility=0.003)
    
    # Extract OR zone (first 15 minutes)
    or_high, or_low = generate_or_zone(bars, or_minutes=15)
    or_mid = (or_high + or_low) / 2
    
    # Define entry after OR (minute 15-30)
    entry_bar_idx = np.random.randint(15, 30)
    entry_bar = bars.iloc[entry_bar_idx]
    
    # Entry price: breakout of OR
    if direction == 'long':
        entry_price = or_high + 0.5  # Breakout above OR
    else:
        entry_price = or_low - 0.5  # Breakout below OR
    
    # Calculate stop and targets
    or_range = or_high - or_low
    stop_distance = max(or_range * 1.2, 2.0)  # Stop beyond OR
    
    if direction == 'long':
        stop_price = entry_price - stop_distance
        target_1 = entry_price + (stop_distance * 1.5)  # 1.5R
        target_2 = entry_price + (stop_distance * 2.0)  # 2R
        target_3 = entry_price + (stop_distance * 3.0)  # 3R
    else:
        stop_price = entry_price + stop_distance
        target_1 = entry_price - (stop_distance * 1.5)
        target_2 = entry_price - (stop_distance * 2.0)
        target_3 = entry_price - (stop_distance * 3.0)
    
    # Determine exit based on realized R
    if realized_r < 0:
        # Hit stop
        exit_price = stop_price
        exit_reason = 'stop'
        exit_bar_idx = entry_bar_idx + np.random.randint(5, 60)
    elif realized_r < 1.0:
        # Partial move then reversal
        exit_price = entry_price + (realized_r * stop_distance * (1 if direction == 'long' else -1))
        exit_reason = 'manual'
        exit_bar_idx = entry_bar_idx + np.random.randint(30, 150)
    elif realized_r < 1.8:
        # Hit T1
        exit_price = target_1
        exit_reason = 'target_1'
        exit_bar_idx = entry_bar_idx + np.random.randint(20, 100)
    elif realized_r < 2.5:
        # Hit T2
        exit_price = target_2
        exit_reason = 'target_2'
        exit_bar_idx = entry_bar_idx + np.random.randint(50, 200)
    else:
        # Hit T3
        exit_price = target_3
        exit_reason = 'target_3'
        exit_bar_idx = entry_bar_idx + np.random.randint(100, 300)
    
    # Ensure exit bar is within day
    exit_bar_idx = min(exit_bar_idx, len(bars) - 1)
    exit_bar = bars.iloc[exit_bar_idx]
    
    # Get bars around the trade (30 bars before entry to exit + 20 after)
    bar_start_idx = max(0, entry_bar_idx - 30)
    bar_end_idx = min(len(bars), exit_bar_idx + 20)
    trade_bars = bars.iloc[bar_start_idx:bar_end_idx].copy()
    
    # Mark entry and exit bars
    trade_bars['is_entry_bar'] = False
    trade_bars['is_exit_bar'] = False
    trade_bars.loc[trade_bars.index[entry_bar_idx - bar_start_idx], 'is_entry_bar'] = True
    trade_bars.loc[trade_bars.index[exit_bar_idx - bar_start_idx], 'is_exit_bar'] = True
    
    # Trade metadata
    trade = {
        'trade_id': trade_id,
        'direction': direction,
        'entry_timestamp': entry_bar['timestamp'],
        'exit_timestamp': exit_bar['timestamp'],
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'realized_r': round(realized_r, 2),
        'stop_price': round(stop_price, 2),
        'target_1': round(target_1, 2),
        'target_2': round(target_2, 2),
        'target_3': round(target_3, 2),
        'or_high': round(or_high, 2),
        'or_low': round(or_low, 2),
        'or_start': day_start,
        'or_end': day_start + timedelta(minutes=15),
        'exit_reason': exit_reason,
        'bars': trade_bars,  # Full bar data for visualization
    }
    
    return trade


def main():
    """Generate realistic trades with full OHLCV data."""
    np.random.seed(42)
    
    # Create run directory
    run_id = "backtest_ohlcv_visualization_20251006"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating trades with full OHLCV data...")
    
    # Generate 20 trades with realistic outcomes
    r_outcomes = [2.0, 1.5, -1.0, 1.8, 0.8, -0.5, 2.5, 1.2, -1.0, 1.0,
                  1.5, 0.5, 2.0, 1.8, -1.0, 1.3, 2.2, -0.8, 1.5, 1.0]
    
    trades_list = []
    all_trades_data = []
    base_price = 570.0
    
    for i, realized_r in enumerate(r_outcomes):
        trade_date = datetime(2025, 9, 30) + timedelta(days=i)
        direction = 'long' if i % 3 != 0 else 'short'
        trade_id = f"ES_{trade_date.strftime('%Y%m%d')}_{i:02d}"
        
        trade = create_trade_with_bars(trade_date, direction, base_price, realized_r, trade_id)
        
        # Save bars for this trade
        bars_file = run_dir / f"{trade_id}_bars.parquet"
        trade['bars'].to_parquet(bars_file)
        
        # Store trade info (without bars for main CSV)
        trade_info = {k: v for k, v in trade.items() if k != 'bars'}
        all_trades_data.append(trade_info)
        
        trades_list.append(trade)
        base_price += np.random.randn() * 1.0  # Slight drift
        
        if (i + 1) % 5 == 0:
            print(f"  Generated {i + 1}/{len(r_outcomes)} trades...")
    
    print(f"✅ Generated {len(trades_list)} trades")
    
    # Create main trades DataFrame
    trades_df = pd.DataFrame(all_trades_data)
    
    # Save trades
    trades_df.to_parquet(run_dir / "SPY_trades.parquet")
    trades_df.to_parquet(run_dir / "all_trades.parquet")
    trades_df.to_csv(run_dir / "all_trades.csv", index=False)
    
    # Create equity curve
    equity_data = []
    cumulative_r = 0.0
    
    for trade in all_trades_data:
        cumulative_r += trade['realized_r']
        equity_data.append({
            'timestamp': trade['exit_timestamp'],
            'cumulative_r': cumulative_r
        })
    
    equity_df = pd.DataFrame(equity_data)
    equity_df.to_parquet(run_dir / "SPY_equity.parquet")
    equity_df.to_parquet(run_dir / "combined_equity.parquet")
    
    # Calculate metrics
    wins = sum(1 for t in all_trades_data if t['realized_r'] > 0)
    losses = len(all_trades_data) - wins
    total_r = sum(t['realized_r'] for t in all_trades_data)
    win_rate = wins / len(all_trades_data)
    expectancy = total_r / len(all_trades_data)
    
    # Calculate drawdown
    running_max = equity_df['cumulative_r'].cummax()
    drawdown = equity_df['cumulative_r'] - running_max
    max_dd = drawdown.min()
    
    # Calculate Sharpe
    returns = [t['realized_r'] for t in all_trades_data]
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
    
    metrics = {
        'symbol': 'ES/SPY',
        'total_trades': len(all_trades_data),
        'win_rate': win_rate,
        'total_r': total_r,
        'expectancy': expectancy,
        'sharpe_ratio': sharpe,
        'max_drawdown_r': max_dd,
        'wins': wins,
        'losses': losses,
    }
    
    with open(run_dir / "SPY_metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    
    # Save config
    config = {
        'run_id': run_id,
        'symbols': ['SPY (ES Proxy)'],
        'period': '2025-09-30 to 2025-10-20',
        'description': 'Full OHLCV data with OR zones and TP/SL levels',
        'has_bar_data': True,
    }
    
    with open(run_dir / "config.json", 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n📊 Metrics:")
    print(f"   Total Trades: {metrics['total_trades']}")
    print(f"   Win Rate: {win_rate:.1%}")
    print(f"   Total R: {total_r:.2f}R")
    print(f"   Expectancy: {expectancy:.3f}R")
    print(f"   Sharpe: {sharpe:.2f}")
    print(f"   Max DD: {max_dd:.2f}R")
    print(f"\n✅ Saved to: runs/{run_id}")
    print(f"   📈 {len(trades_list)} trade bar files created")
    print(f"\n🎨 Refresh dashboard and select '{run_id}'!")


if __name__ == '__main__':
    main()
