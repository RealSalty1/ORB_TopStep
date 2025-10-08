"""
Fetch 1-minute OHLCV data for futures contracts from Yahoo Finance.

Yahoo Finance limits:
- 1-minute data: Last 7 days
- We'll try to fetch as far back as possible
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import json
from pathlib import Path
from loguru import logger


# Futures symbols mapping
FUTURES_SYMBOLS = {
    'ES': 'ES=F',  # E-mini S&P 500
    'NQ': 'NQ=F',  # E-mini Nasdaq-100
    'CL': 'CL=F',  # Crude Oil
    'GC': 'GC=F',  # Gold
    '6E': '6E=F',  # Euro FX
}


def get_display_name(symbol: str) -> str:
    """Get full display name for symbol."""
    names = {
        'ES': 'E-mini S&P 500',
        'NQ': 'E-mini Nasdaq-100',
        'CL': 'Crude Oil',
        'GC': 'Gold',
        '6E': 'Euro FX'
    }
    return names.get(symbol, symbol)


def setup_logging():
    """Configure loguru logger."""
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )


def fetch_intraday(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str = '1m',
    max_retries: int = 3
) -> pd.DataFrame:
    """
    Fetch intraday data from Yahoo Finance with retry logic.
    
    Args:
        symbol: Yahoo Finance symbol (e.g., 'ES=F')
        start: Start datetime
        end: End datetime
        interval: Data interval ('1m', '2m', '5m', '15m', '1h', '1d')
        max_retries: Maximum number of retry attempts
        
    Returns:
        DataFrame with columns: timestamp_utc, open, high, low, close, volume
    """
    logger.info(f"Fetching {interval} data for {symbol} from {start.date()} to {end.date()}")
    
    for attempt in range(max_retries):
        try:
            # Format dates for yfinance
            start_str = start.strftime('%Y-%m-%d')
            end_str = end.strftime('%Y-%m-%d')
            
            # Download data
            df = yf.download(
                symbol,
                start=start_str,
                end=end_str,
                interval=interval,
                progress=False,
                auto_adjust=True
            )
            
            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return None
            
            # Reset index to make Datetime a column
            df = df.reset_index()
            
            # Rename columns to our standard format
            df = df.rename(columns={
                'Datetime': 'timestamp_utc',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Ensure timestamp is timezone-aware UTC
            if df['timestamp_utc'].dt.tz is None:
                df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc']).dt.tz_localize('UTC')
            else:
                df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc']).dt.tz_convert('UTC')
            
            # Sort by timestamp
            df = df.sort_values('timestamp_utc').reset_index(drop=True)
            
            # Add source column
            df['symbol'] = symbol
            df['source'] = 'yahoo'
            
            logger.success(f"Successfully fetched {len(df)} bars for {symbol}")
            return df
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to fetch data for {symbol} after {max_retries} attempts")
                return None


def main():
    """Fetch 1-minute futures data for all symbols."""
    setup_logging()
    
    print("\n" + "="*80)
    print("FETCHING 1-MINUTE FUTURES DATA")
    print("="*80)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Create output directory
    output_dir = Path('data_cache/futures_1m')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate date range (last 7 days for 1-minute data)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
    print(f"📊 Interval: 1m (1-minute bars)")
    print(f"📁 Output directory: {output_dir}")
    print(f"🎯 Symbols: {', '.join(FUTURES_SYMBOLS.keys())}\n")
    print("="*80 + "\n")
    
    results = {}
    
    for short_name, yahoo_symbol in FUTURES_SYMBOLS.items():
        print(f"🔄 Fetching {short_name} ({yahoo_symbol})...")
        
        bars = fetch_intraday(
            symbol=yahoo_symbol,
            start=start_date,
            end=end_date,
            interval='1m'
        )
        
        if bars is None or len(bars) == 0:
            print(f"   ❌ No data returned for {short_name}\n")
            results[short_name] = {'success': False, 'bars': 0}
            continue
        
        print(f"   ✅ Received {len(bars):,} bars")
        
        # Handle timestamp column name
        timestamp_col = 'timestamp_utc' if 'timestamp_utc' in bars.columns else 'timestamp'
        
        print(f"   📊 Date range: {bars[timestamp_col].min()} to {bars[timestamp_col].max()}")
        min_price = float(bars['close'].min())
        max_price = float(bars['close'].max())
        print(f"   💲 Price range: ${min_price:.2f} - ${max_price:.2f}")
        
        # Convert timestamp to ISO format string for JSON
        bars_dict = bars.copy()
        
        # Flatten any multi-index columns
        if isinstance(bars_dict.columns, pd.MultiIndex):
            bars_dict.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in bars_dict.columns]
        
        # Debug: Print actual columns
        print(f"   🔍 Columns after flattening: {list(bars_dict.columns)}")
        
        # Ensure we have the required columns (case-insensitive search)
        col_map = {}
        for col in bars_dict.columns:
            col_lower = str(col).lower()
            if 'timestamp' in col_lower:
                col_map['timestamp_src'] = col
            # Handle columns like 'close_ES=F', 'open_ES=F', etc.
            elif any(key in col_lower for key in ['open', 'high', 'low', 'close', 'volume']):
                for key in ['open', 'high', 'low', 'close', 'volume']:
                    if col_lower.startswith(key):
                        col_map[key] = col
                        break
        
        print(f"   🗺️  Column mapping: {col_map}")
        
        # Create clean dataset with standard column names
        clean_data = pd.DataFrame()
        clean_data['timestamp'] = pd.to_datetime(bars_dict[col_map.get('timestamp_src', timestamp_col)]).dt.strftime('%Y-%m-%d %H:%M:%S')
        clean_data['open'] = bars_dict[col_map['open']]
        clean_data['high'] = bars_dict[col_map['high']]
        clean_data['low'] = bars_dict[col_map['low']]
        clean_data['close'] = bars_dict[col_map['close']]
        clean_data['volume'] = bars_dict[col_map['volume']]
        clean_data['symbol'] = short_name
        clean_data['source'] = 'yahoo'
        
        bars_dict = clean_data
        
        # Create metadata
        data = {
            'symbol': short_name,
            'yahoo_symbol': yahoo_symbol,
            'display_name': get_display_name(short_name),
            'interval': '1m',
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'fetch_timestamp': datetime.utcnow().isoformat(),
            'bar_count': len(bars),
            'actual_date_range': {
                'start': str(bars[timestamp_col].min()),
                'end': str(bars[timestamp_col].max())
            },
            'data': bars_dict.to_dict(orient='records')
        }
        
        # Save to JSON
        output_file = output_dir / f"{short_name}_1m.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"   💾 Saved to: {output_file.name} ({file_size_mb:.1f} MB)")
        
        results[short_name] = {
            'success': True,
            'bars': len(bars),
            'file_size_mb': file_size_mb
        }
        
        print()
        
        # Rate limiting - wait 5 seconds between requests
        if short_name != list(FUTURES_SYMBOLS.keys())[-1]:  # Don't wait after last symbol
            print("   ⏳ Waiting 5 seconds to avoid rate limits...")
            time.sleep(5)
            print()
    
    # Print summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    
    total_bars = sum(r['bars'] for r in results.values() if r['success'])
    total_size = sum(r['file_size_mb'] for r in results.values() if r['success'])
    successful = sum(1 for r in results.values() if r['success'])
    
    print(f"\n✅ Successfully fetched: {successful}/{len(FUTURES_SYMBOLS)} symbols")
    print(f"📊 Total bars: {total_bars:,}")
    print(f"💾 Total storage: {total_size:.1f} MB")
    
    print("\n📋 Per-symbol breakdown:")
    for symbol, result in results.items():
        if result['success']:
            print(f"   • {symbol}: {result['bars']:,} bars ({result['file_size_mb']:.1f} MB)")
        else:
            print(f"   • {symbol}: ❌ Failed")
    
    print(f"\n✅ Data cached to: {output_dir}")
    print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
