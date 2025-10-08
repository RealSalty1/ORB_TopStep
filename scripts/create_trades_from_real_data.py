#!/usr/bin/env python3
"""Create trades from real Yahoo Finance data by identifying actual breakouts."""

import sys
sys.path.insert(0, '.')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json

from orb_confluence.data import YahooProvider


def identify_or_breakouts(bars_day: pd.DataFrame, or_minutes: int = 15) -> list:
    """Identify actual OR breakouts in real data.
    
    Args:
        bars_day: DataFrame for a single day
        or_minutes: OR duration
        
    Returns:
        List of trade dictionaries
    """
    if len(bars_day) < or_minutes + 10:  # Need enough bars
        return []
    
    # Calculate OR
    or_bars = bars_day.iloc[:or_minutes]
    or_high = or_bars['high'].max()
    or_low = or_bars['low'].min()
    or_start = bars_day['timestamp'].iloc[0]
    or_end = bars_day['timestamp'].iloc[or_minutes-1]
    
    # Look for breakouts after OR
    breakouts = []
    bars_after_or = bars_day.iloc[or_minutes:]
    
    long_triggered = False
    short_triggered = False
    
    for i, bar in bars_after_or.iterrows():
        # Long breakout
        if not long_triggered and bar['high'] > or_high + 0.2:  # 20 cent buffer
            # Found a long breakout
            entry_price = or_high + 0.2
            stop_distance = max((or_high - or_low) * 1.2, 2.0)
            stop_price = entry_price - stop_distance
            
            # Look ahead for exit (simplified: look for stop or target hit)
            exit_idx = None
            exit_price = None
            exit_reason = None
            
            target_1 = entry_price + (stop_distance * 1.5)
            target_2 = entry_price + (stop_distance * 2.0)
            
            # Scan forward
            for j in range(i, len(bars_day)):
                future_bar = bars_day.iloc[j]
                
                # Check stop hit
                if future_bar['low'] <= stop_price:
                    exit_idx = j
                    exit_price = stop_price
                    exit_reason = 'stop'
                    break
                
                # Check target hit
                if future_bar['high'] >= target_1:
                    exit_idx = j
                    exit_price = target_1
                    exit_reason = 'target_1'
                    break
            
            # If no exit found, use end of day
            if exit_idx is None:
                exit_idx = len(bars_day) - 1
                exit_price = bars_day.iloc[exit_idx]['close']
                exit_reason = 'eod'
            
            # Calculate R
            realized_r = (exit_price - entry_price) / stop_distance
            
            trade = {
                'direction': 'long',
                'entry_timestamp': bar['timestamp'],
                'entry_price': entry_price,
                'exit_timestamp': bars_day.iloc[exit_idx]['timestamp'],
                'exit_price': exit_price,
                'stop_price': stop_price,
                'target_1': target_1,
                'target_2': target_2,
                'target_3': entry_price + (stop_distance * 3.0),
                'or_high': or_high,
                'or_low': or_low,
                'or_start': or_start,
                'or_end': or_end,
                'realized_r': realized_r,
                'exit_reason': exit_reason,
            }
            
            breakouts.append(trade)
            long_triggered = True
        
        # Short breakout
        if not short_triggered and bar['low'] < or_low - 0.2:  # 20 cent buffer
            entry_price = or_low - 0.2
            stop_distance = max((or_high - or_low) * 1.2, 2.0)
            stop_price = entry_price + stop_distance
            
            exit_idx = None
            exit_price = None
            exit_reason = None
            
            target_1 = entry_price - (stop_distance * 1.5)
            target_2 = entry_price - (stop_distance * 2.0)
            
            # Scan forward
            for j in range(i, len(bars_day)):
                future_bar = bars_day.iloc[j]
                
                # Check stop hit
                if future_bar['high'] >= stop_price:
                    exit_idx = j
                    exit_price = stop_price
                    exit_reason = 'stop'
                    break
                
                # Check target hit
                if future_bar['low'] <= target_1:
                    exit_idx = j
                    exit_price = target_1
                    exit_reason = 'target_1'
                    break
            
            # If no exit found, use end of day
            if exit_idx is None:
                exit_idx = len(bars_day) - 1
                exit_price = bars_day.iloc[exit_idx]['close']
                exit_reason = 'eod'
            
            # Calculate R
            realized_r = (entry_price - exit_price) / stop_distance
            
            trade = {
                'direction': 'short',
                'entry_timestamp': bar['timestamp'],
                'entry_price': entry_price,
                'exit_timestamp': bars_day.iloc[exit_idx]['timestamp'],
                'exit_price': exit_price,
                'stop_price': stop_price,
                'target_1': target_1,
                'target_2': target_2,
                'target_3': entry_price - (stop_distance * 3.0),
                'or_high': or_high,
                'or_low': or_low,
                'or_start': or_start,
                'or_end': or_end,
                'realized_r': realized_r,
                'exit_reason': exit_reason,
            }
            
            breakouts.append(trade)
            short_triggered = True
    
    return breakouts


def main():
    """Generate trades from real Yahoo Finance data."""
    print("\n" + "="*80)
    print("REAL DATA TRADE EXTRACTION - Yahoo Finance SPY")
    print("="*80 + "\n")
    
    # Fetch real data
    print("📊 Fetching real market data from Yahoo Finance...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    provider = YahooProvider()
    
    # Try ES futures first, fallback to SPY if not available
    symbol = 'ES=F'  # E-mini S&P 500 futures
    print(f"   Attempting to fetch {symbol} (E-mini S&P 500 Futures)...")
    
    bars = provider.fetch_intraday(
        symbol=symbol,
        start=start_date,
        end=end_date,
        interval='1m'
    )
    
    # If ES=F fails, try SPY as fallback
    if bars is None or len(bars) == 0:
        print(f"   {symbol} not available, falling back to SPY...")
        symbol = 'SPY'
        bars = provider.fetch_intraday(
            symbol=symbol,
            start=start_date,
            end=end_date,
            interval='1m'
        )
    
    if bars is None or len(bars) == 0:
        print("❌ Failed to fetch data")
        return 1
    
    # Add timestamp column
    if 'timestamp_utc' in bars.columns and 'timestamp' not in bars.columns:
        bars['timestamp'] = bars['timestamp_utc']
    
    print(f"✅ Fetched {len(bars)} bars for {symbol}")
    print(f"   Date range: {bars['timestamp'].min().date()} to {bars['timestamp'].max().date()}")
    print(f"   Price range: ${bars['close'].min():.2f} - ${bars['close'].max():.2f}")
    
    # Group by day
    bars['date'] = bars['timestamp'].dt.date
    days = bars.groupby('date')
    
    print(f"\n🔍 Analyzing {len(days)} trading days for breakouts...")
    
    # Find breakouts in each day
    all_trades = []
    for date, bars_day in days:
        bars_day = bars_day.reset_index(drop=True)
        breakouts = identify_or_breakouts(bars_day)
        
        if breakouts:
            print(f"   ✓ {date}: Found {len(breakouts)} breakout(s)")
            for trade in breakouts:
                # Use actual symbol in trade ID
                symbol_clean = symbol.replace('=', '').replace('-', '')
                trade['trade_id'] = f"{symbol_clean}_{date.strftime('%Y%m%d')}_{trade['direction']}"
                all_trades.append(trade)
                
                # Save bar data for this trade
                # (bars_day already contains all the day's data)
        else:
            print(f"     {date}: No breakouts")
    
    if not all_trades:
        print("\n❌ No breakouts found in real data!")
        print("   Try a more volatile market period or adjust breakout thresholds.")
        return 1
    
    print(f"\n✅ Found {len(all_trades)} real breakout trades!")
    
    # Create run directory with symbol in name
    symbol_clean = symbol.replace('=', '').replace('-', '')
    run_id = f"backtest_{symbol_clean}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n💾 Saving to: {run_id}")
    
    # Save trades
    trades_df = pd.DataFrame(all_trades)
    symbol_file_prefix = f"{symbol_clean}_trades.parquet"
    trades_df.to_parquet(run_dir / symbol_file_prefix)
    trades_df.to_parquet(run_dir / "all_trades.parquet")
    trades_df.to_csv(run_dir / "all_trades.csv", index=False)
    
    # Save bar data for each trade
    for trade in all_trades:
        entry_ts = pd.to_datetime(trade['entry_timestamp'])
        exit_ts = pd.to_datetime(trade['exit_timestamp'])
        
        # Get bars ±30 min around trade
        start_ts = entry_ts - timedelta(minutes=30)
        end_ts = exit_ts + timedelta(minutes=20)
        
        trade_bars = bars[
            (bars['timestamp'] >= start_ts) & 
            (bars['timestamp'] <= end_ts)
        ].copy()
        
        if len(trade_bars) > 0:
            bars_file = run_dir / f"{trade['trade_id']}_bars.parquet"
            trade_bars.to_parquet(bars_file)
            print(f"   ✓ Saved bars for {trade['trade_id']}")
    
    # Create equity curve
    equity_data = []
    cumulative_r = 0.0
    for trade in all_trades:
        cumulative_r += trade['realized_r']
        equity_data.append({
            'timestamp': trade['exit_timestamp'],
            'cumulative_r': cumulative_r
        })
    
    equity_df = pd.DataFrame(equity_data)
    equity_df.to_parquet(run_dir / f"{symbol_clean}_equity.parquet")
    equity_df.to_parquet(run_dir / "combined_equity.parquet")
    
    # Calculate metrics
    wins = sum(1 for t in all_trades if t['realized_r'] > 0)
    losses = len(all_trades) - wins
    total_r = sum(t['realized_r'] for t in all_trades)
    win_rate = wins / len(all_trades) if all_trades else 0
    expectancy = total_r / len(all_trades) if all_trades else 0
    
    # Calculate drawdown
    running_max = equity_df['cumulative_r'].cummax()
    drawdown = equity_df['cumulative_r'] - running_max
    max_dd = drawdown.min() if len(drawdown) > 0 else 0
    
    # Calculate Sharpe
    returns = [t['realized_r'] for t in all_trades]
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
    
    # Determine symbol display name
    symbol_display = 'E-mini S&P 500 Futures (ES)' if symbol == 'ES=F' else symbol
    
    metrics = {
        'symbol': symbol_display,
        'data_source': 'Yahoo Finance (Real Market Data)',
        'total_trades': len(all_trades),
        'win_rate': win_rate,
        'total_r': total_r,
        'expectancy': expectancy,
        'sharpe_ratio': sharpe,
        'max_drawdown_r': max_dd,
        'wins': wins,
        'losses': losses,
        'start_date': str(start_date.date()),
        'end_date': str(end_date.date()),
    }
    
    with open(run_dir / f"{symbol_clean}_metrics.json", 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    
    # Save config
    config_data = {
        'run_id': run_id,
        'symbols': [symbol_display],
        'data_source': 'Yahoo Finance - Real Market Data',
        'period': f"{start_date.date()} to {end_date.date()}",
        'description': f'Real ORB breakouts from {symbol_display}',
        'has_bar_data': True,
        'bars_count': len(bars),
        'method': 'Manual breakout identification',
    }
    
    with open(run_dir / "config.json", 'w') as f:
        json.dump(config_data, f, indent=2)
    
    print(f"\n✅ Complete!")
    print(f"\n📊 Performance Summary - {symbol_display}:")
    print(f"   Trades: {len(all_trades)}")
    print(f"   Win Rate: {win_rate:.1%}")
    print(f"   Total R: {total_r:.2f}R")
    print(f"   Expectancy: {expectancy:.3f}R")
    print(f"   Max DD: {max_dd:.2f}R")
    print(f"\n📁 Results saved to: runs/{run_id}")
    print(f"\n🎨 View in dashboard:")
    print(f"   1. Refresh browser at http://localhost:8501")
    print(f"   2. Select run: {run_id}")
    print(f"   3. Navigate to 'Trade Charts' page")
    print(f"   4. See REAL {symbol_display} data with REAL breakouts!")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
