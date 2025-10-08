#!/usr/bin/env python3
"""Run backtest with real Yahoo Finance data and save bar data for each trade."""

import sys
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json

from orb_confluence.config import load_config
from orb_confluence.data import YahooProvider
from orb_confluence.backtest import EventLoopBacktest
from orb_confluence.analytics import compute_metrics


def save_trade_bars(trade, all_bars: pd.DataFrame, run_dir: Path):
    """Extract and save bar data around a trade.
    
    Args:
        trade: ActiveTrade object
        all_bars: Full DataFrame of bars
        run_dir: Directory to save to
    """
    entry_ts = pd.to_datetime(trade.entry_timestamp)
    exit_ts = pd.to_datetime(trade.exit_timestamp)
    
    # Get bars from 30 minutes before entry to 20 minutes after exit
    start_ts = entry_ts - timedelta(minutes=30)
    end_ts = exit_ts + timedelta(minutes=20)
    
    # Filter bars
    bars_subset = all_bars[
        (all_bars['timestamp'] >= start_ts) & 
        (all_bars['timestamp'] <= end_ts)
    ].copy()
    
    if len(bars_subset) > 0:
        # Save to parquet
        bars_file = run_dir / f"{trade.trade_id}_bars.parquet"
        bars_subset.to_parquet(bars_file)
        return True
    
    return False


def main():
    """Run backtest with real Yahoo Finance data."""
    print("\n" + "="*80)
    print("REAL DATA BACKTEST - Yahoo Finance SPY")
    print("="*80 + "\n")
    
    # Load config with VERY low requirements to ensure trades
    config = load_config('config_low_requirements.yaml')
    
    # Fetch real data from Yahoo (last 7 days - that's the limit for 1min data)
    print("📊 Fetching real market data from Yahoo Finance...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    provider = YahooProvider()
    bars = provider.fetch_intraday(
        symbol='SPY',
        start=start_date,
        end=end_date,
        interval='1m'
    )
    
    if bars is None or len(bars) == 0:
        print("❌ Failed to fetch data from Yahoo Finance")
        return 1
    
    # Add timestamp column for compatibility (event loop uses timestamp_utc)
    if 'timestamp_utc' in bars.columns and 'timestamp' not in bars.columns:
        bars['timestamp'] = bars['timestamp_utc']
    
    print(f"✅ Fetched {len(bars)} bars from {bars['timestamp_utc'].min()} to {bars['timestamp_utc'].max()}")
    print(f"   Date range: {start_date.date()} to {end_date.date()}")
    print(f"   Price range: ${bars['close'].min():.2f} - ${bars['close'].max():.2f}")
    
    # Run backtest
    print("\n🔄 Running backtest with real data...")
    engine = EventLoopBacktest(config)
    result = engine.run(bars)
    
    print(f"\n📊 Backtest Results:")
    print(f"   Total trades: {result.total_trades}")
    print(f"   Total R: {result.total_r:.2f}R")
    
    if result.total_trades == 0:
        print("\n⚠️  No trades generated with current config.")
        print("   This could mean:")
        print("   - Market didn't break out of OR during this period")
        print("   - Confluence requirements still too strict")
        print("   - OR validation too strict")
        return 1
    
    # Create run directory
    run_id = f"backtest_real_yahoo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n💾 Saving results to: {run_id}")
    
    # Prepare trades data with full metadata
    trades_data = []
    for trade in result.trades:
        # Get OR data if available
        or_high = None
        or_low = None
        or_start = None
        or_end = None
        
        if hasattr(trade, 'signal') and trade.signal:
            or_high = trade.signal.or_high
            or_low = trade.signal.or_low
            or_start = trade.entry_timestamp.replace(hour=9, minute=30, second=0)
            or_end = or_start + timedelta(minutes=15)
        
        # Calculate stop and targets (simplified)
        stop_distance = abs(trade.entry_price - trade.stop_price_initial)
        
        if trade.direction == 'long':
            target_1 = trade.entry_price + (stop_distance * 1.5)
            target_2 = trade.entry_price + (stop_distance * 2.0)
            target_3 = trade.entry_price + (stop_distance * 3.0)
        else:
            target_1 = trade.entry_price - (stop_distance * 1.5)
            target_2 = trade.entry_price - (stop_distance * 2.0)
            target_3 = trade.entry_price - (stop_distance * 3.0)
        
        trade_data = {
            'trade_id': trade.trade_id,
            'direction': trade.direction,
            'entry_timestamp': trade.entry_timestamp,
            'exit_timestamp': trade.exit_timestamp,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price if trade.exit_price else trade.entry_price,
            'realized_r': trade.realized_r if trade.realized_r else 0.0,
            'stop_price': trade.stop_price_initial,
            'target_1': target_1,
            'target_2': target_2,
            'target_3': target_3,
            'or_high': or_high,
            'or_low': or_low,
            'or_start': or_start,
            'or_end': or_end,
            'exit_reason': trade.exit_reason if hasattr(trade, 'exit_reason') else 'unknown',
        }
        
        trades_data.append(trade_data)
        
        # Save bar data for this trade
        saved = save_trade_bars(trade, bars, run_dir)
        if saved:
            print(f"   ✓ Saved bars for trade {trade.trade_id}")
    
    # Create trades DataFrame
    trades_df = pd.DataFrame(trades_data)
    
    # Save trades
    trades_df.to_parquet(run_dir / "SPY_trades.parquet")
    trades_df.to_parquet(run_dir / "all_trades.parquet")
    trades_df.to_csv(run_dir / "all_trades.csv", index=False)
    
    # Save equity curve
    result.equity_curve.to_parquet(run_dir / "SPY_equity.parquet")
    result.equity_curve.to_parquet(run_dir / "combined_equity.parquet")
    
    # Calculate metrics
    metrics = compute_metrics(result.trades)
    
    metrics_dict = {
        'symbol': 'SPY',
        'data_source': 'Yahoo Finance (Real Market Data)',
        'total_trades': metrics.total_trades,
        'win_rate': metrics.win_rate,
        'total_r': metrics.total_r,
        'expectancy': metrics.expectancy,
        'sharpe_ratio': metrics.sharpe_ratio if metrics.sharpe_ratio else 0.0,
        'max_drawdown_r': metrics.max_drawdown_r,
        'wins': sum(1 for t in result.trades if t.realized_r and t.realized_r > 0),
        'losses': sum(1 for t in result.trades if t.realized_r and t.realized_r <= 0),
        'start_date': str(start_date.date()),
        'end_date': str(end_date.date()),
    }
    
    with open(run_dir / "SPY_metrics.json", 'w') as f:
        json.dump(metrics_dict, f, indent=2, default=str)
    
    # Save config
    config_data = {
        'run_id': run_id,
        'symbols': ['SPY'],
        'data_source': 'Yahoo Finance',
        'period': f"{start_date.date()} to {end_date.date()}",
        'description': 'Real market data backtest',
        'has_bar_data': True,
        'bars_count': len(bars),
    }
    
    with open(run_dir / "config.json", 'w') as f:
        json.dump(config_data, f, indent=2)
    
    print(f"\n✅ Backtest complete!")
    print(f"\n📊 Performance Summary:")
    print(f"   Trades: {metrics.total_trades}")
    print(f"   Win Rate: {metrics.win_rate:.1%}")
    print(f"   Total R: {metrics.total_r:.2f}R")
    print(f"   Expectancy: {metrics.expectancy:.3f}R")
    print(f"   Max DD: {metrics.max_drawdown_r:.2f}R")
    print(f"\n📁 Results saved to: runs/{run_id}")
    print(f"\n🎨 View in dashboard:")
    print(f"   1. Refresh browser at http://localhost:8501")
    print(f"   2. Select run: {run_id}")
    print(f"   3. Navigate to 'Trade Charts' page")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
