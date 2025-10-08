#!/usr/bin/env python3
"""Fetch 15-minute OHLCV data for futures contracts from Yahoo Finance.

This script fetches historical data for multiple futures contracts and saves
them as JSON files in the data cache directory.
"""

import sys
sys.path.insert(0, '.')

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from orb_confluence.data import YahooProvider


# Futures symbols to fetch
FUTURES_SYMBOLS = {
    'ES': 'ES=F',  # E-mini S&P 500
    'NQ': 'NQ=F',  # E-mini NASDAQ 100
    'CL': 'CL=F',  # Crude Oil
    'GC': 'GC=F',  # Gold
    '6E': '6E=F',  # Euro FX
}

DISPLAY_NAMES = {
    'ES': 'E-mini S&P 500',
    'NQ': 'E-mini NASDAQ 100',
    'CL': 'Crude Oil',
    'GC': 'Gold',
    '6E': 'Euro FX',
}

# Configuration
INTERVAL = '15m'
DAYS_BACK = 30
DELAY_BETWEEN_REQUESTS = 5  # seconds
OUTPUT_DIR = Path('data_cache/futures_15m')


def fetch_and_save_futures_data():
    """Fetch data for all futures and save to JSON."""
    
    print("="*80)
    print("FUTURES DATA FETCH - 15 Minute OHLCV")
    print("="*80)
    print()
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=DAYS_BACK)
    
    print(f"📅 Date Range: {start_date.date()} to {end_date.date()}")
    print(f"⏱️  Interval: {INTERVAL}")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"⏳ Delay between requests: {DELAY_BETWEEN_REQUESTS}s")
    print()
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize provider
    provider = YahooProvider()
    
    total_symbols = len(FUTURES_SYMBOLS)
    
    for idx, (short_name, yahoo_symbol) in enumerate(FUTURES_SYMBOLS.items(), 1):
        display_name = DISPLAY_NAMES[short_name]
        
        print(f"\n[{idx}/{total_symbols}] Fetching {short_name} ({display_name})...")
        print(f"   Yahoo Symbol: {yahoo_symbol}")
        
        try:
            # Fetch data
            print(f"   Requesting data from Yahoo Finance...")
            bars = provider.fetch_intraday(
                symbol=yahoo_symbol,
                start=start_date,
                end=end_date,
                interval=INTERVAL
            )
            
            if bars is None or len(bars) == 0:
                print(f"   ❌ No data returned for {short_name}")
                continue
            
            # Convert to JSON-friendly format
            print(f"   ✅ Received {len(bars)} bars")
            
            # Handle timestamp column name (could be 'timestamp' or 'timestamp_utc')
            timestamp_col = 'timestamp_utc' if 'timestamp_utc' in bars.columns else 'timestamp'
            
            print(f"   📊 Date range: {bars[timestamp_col].min()} to {bars[timestamp_col].max()}")
            print(f"   💲 Price range: ${bars['close'].min():.2f} - ${bars['close'].max():.2f}")
            
            # Convert timestamp to ISO format string
            bars_dict = bars.copy()
            bars_dict['timestamp'] = bars_dict[timestamp_col].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Drop the original timestamp column if it's different
            if timestamp_col != 'timestamp' and timestamp_col in bars_dict.columns:
                bars_dict = bars_dict.drop(columns=[timestamp_col])
            
            # Convert to records format
            data = {
                'symbol': short_name,
                'yahoo_symbol': yahoo_symbol,
                'display_name': display_name,
                'interval': INTERVAL,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'fetch_timestamp': datetime.now().isoformat(),
                'bar_count': len(bars),
                'data': bars_dict.to_dict('records')
            }
            
            # Save to JSON
            output_file = OUTPUT_DIR / f"{short_name}_15m.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            print(f"   💾 Saved to: {output_file}")
            print(f"   📦 File size: {output_file.stat().st_size / 1024:.2f} KB")
            
            # Delay before next request (except for last one)
            if idx < total_symbols:
                print(f"\n   ⏳ Waiting {DELAY_BETWEEN_REQUESTS}s before next request...")
                time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            print(f"   ❌ Error fetching {short_name}: {e}")
            print(f"   Continuing with next symbol...")
            continue
    
    print("\n" + "="*80)
    print("✅ DATA FETCH COMPLETE")
    print("="*80)
    
    # Summary
    print("\n📊 Summary:")
    saved_files = list(OUTPUT_DIR.glob("*.json"))
    print(f"   Total files saved: {len(saved_files)}")
    
    total_size = sum(f.stat().st_size for f in saved_files)
    print(f"   Total size: {total_size / 1024:.2f} KB")
    
    print("\n📁 Saved files:")
    for file in sorted(saved_files):
        print(f"   - {file.name}")
    
    print(f"\n📍 Location: {OUTPUT_DIR.absolute()}")
    
    return 0


if __name__ == '__main__':
    sys.exit(fetch_and_save_futures_data())
