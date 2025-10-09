"""Create multi-timeframe data from 1-minute Databento data.

Resamples 1m data to 5m, 15m, 30m, and 1h intervals.
"""

import json
from pathlib import Path
from datetime import datetime
import pandas as pd
from loguru import logger


def resample_ohlcv(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample OHLCV data to a different frequency.
    
    Args:
        df: DataFrame with timestamp_utc, open, high, low, close, volume
        freq: Pandas frequency string (5T, 15T, 30T, 1H, etc.)
        
    Returns:
        Resampled DataFrame
    """
    # Set timestamp as index
    df = df.set_index('timestamp_utc')
    
    # Resample with proper OHLCV aggregation
    resampled = df.resample(freq).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })
    
    # Drop any rows with NaN (incomplete bars at the end)
    resampled = resampled.dropna()
    
    # Reset index
    resampled = resampled.reset_index()
    
    return resampled


def save_to_json(df: pd.DataFrame, output_path: Path, symbol: str, interval: str):
    """Save DataFrame to Databento JSON format.
    
    Args:
        df: DataFrame with timestamp_utc, open, high, low, close, volume
        output_path: Path to save JSON file
        symbol: Instrument symbol
        interval: Interval string (5m, 15m, 30m, 1h)
    """
    # Convert DataFrame to records
    records = []
    for _, row in df.iterrows():
        records.append({
            'timestamp': row['timestamp_utc'].isoformat(),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row['volume'])
        })
    
    # Create JSON structure
    json_data = {
        'symbol': symbol,
        'interval': interval,
        'bar_count': len(records),
        'start_date': df['timestamp_utc'].min().strftime('%Y-%m-%d'),
        'end_date': df['timestamp_utc'].max().strftime('%Y-%m-%d'),
        'data': records
    }
    
    # Save to file
    logger.info(f"Writing {len(records)} bars to {output_path}")
    with open(output_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    file_size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(f"Saved {output_path} ({file_size_mb:.1f} MB)")


def create_multi_timeframe_data(symbol: str = "ES"):
    """Create multi-timeframe data files for a symbol.
    
    Args:
        symbol: Instrument symbol (default: ES)
    """
    # Paths
    data_dir = Path("data_cache")
    input_file = data_dir / "databento_1m" / f"{symbol}_1m.json"
    
    # Create output directories
    for interval in ['5m', '15m', '30m', '1h']:
        output_dir = data_dir / f"databento_{interval}"
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load 1m data
    logger.info(f"Loading {input_file} ({input_file.stat().st_size / 1024 / 1024:.1f} MB)")
    with open(input_file, 'r') as f:
        json_data = json.load(f)
    
    logger.info(f"Metadata: {json_data['symbol']}, {json_data['bar_count']} bars")
    logger.info(f"Date range: {json_data['start_date']} to {json_data['end_date']}")
    
    # Convert to DataFrame
    records = []
    for record in json_data['data']:
        records.append({
            'timestamp_utc': pd.Timestamp(record['timestamp'], tz='UTC'),
            'open': float(record['open']),
            'high': float(record['high']),
            'low': float(record['low']),
            'close': float(record['close']),
            'volume': int(record['volume'])
        })
    
    df_1m = pd.DataFrame(records)
    df_1m = df_1m.sort_values('timestamp_utc').reset_index(drop=True)
    logger.info(f"Loaded {len(df_1m)} bars for {symbol}")
    logger.info(f"Range: {df_1m['timestamp_utc'].min()} to {df_1m['timestamp_utc'].max()}")
    
    # Resample to different timeframes
    timeframes = {
        '5m': '5T',   # 5 minutes
        '15m': '15T', # 15 minutes
        '30m': '30T', # 30 minutes
        '1h': '1H'    # 1 hour
    }
    
    for interval, freq in timeframes.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Creating {interval} data for {symbol}")
        logger.info(f"{'='*60}")
        
        # Resample
        df_resampled = resample_ohlcv(df_1m.copy(), freq)
        logger.info(f"Resampled to {len(df_resampled)} bars ({interval})")
        
        # Save to JSON
        output_dir = data_dir / f"databento_{interval}"
        output_file = output_dir / f"{symbol}_{interval}.json"
        save_to_json(df_resampled, output_file, symbol, interval)
    
    logger.info(f"\n{'='*60}")
    logger.info("Multi-timeframe data creation complete!")
    logger.info(f"{'='*60}")
    
    # Summary
    logger.info("\nSummary:")
    logger.info(f"  1m:  {len(df_1m)} bars")
    for interval, freq in timeframes.items():
        output_file = data_dir / f"databento_{interval}" / f"{symbol}_{interval}.json"
        if output_file.exists():
            with open(output_file, 'r') as f:
                data = json.load(f)
            logger.info(f"  {interval:3s}: {data['bar_count']} bars ({output_file.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    logger.info("Creating multi-timeframe data for ES")
    create_multi_timeframe_data("ES")
    logger.info("\nDone!")

