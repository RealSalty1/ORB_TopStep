"""
Convert Databento CSV.zst files to JSON format for our backtest platform.

This script:
1. Decompresses zstd-compressed CSV files from Databento
2. Converts to our expected schema (timestamp, open, high, low, close, volume)
3. Handles continuous contract construction (front-month rolling)
4. Saves as JSON files matching our existing data structure
"""

import pandas as pd
import zstandard as zstd
import json
from pathlib import Path
from datetime import datetime
import sys
from loguru import logger

# Symbol mapping: our internal name -> Databento parent symbol
INSTRUMENT_MAPPING = {
    'ES': 'ES.FUT',  # E-mini S&P 500
    'NQ': 'MNQ.FUT', # Micro E-mini Nasdaq (since we likely have MNQ data)
    'GC': 'GC.FUT',  # Gold
    '6E': '6E.FUT',  # Euro
}

# Databento folder mapping (fixed based on contract symbols in output)
DATABENTO_FOLDERS = {
    '6E': 'GLBX-20251007-4TPUEMQFH3',
    'ES': 'GLBX-20251007-8KTBLG4NJA',
    'NQ': 'GLBX-20251007-UJ6YXEVHJA',  # MNQ (Micro Nasdaq)
    'GC': 'GLBX-20251007-CYEDDDU8C8',  # GC (Gold)
}

def decompress_zst_file(zst_path: Path, output_csv_path: Path):
    """Decompress a zstandard file."""
    logger.info(f"Decompressing {zst_path.name}...")
    
    dctx = zstd.ZstdDecompressor()
    
    with open(zst_path, 'rb') as compressed:
        with open(output_csv_path, 'wb') as decompressed:
            dctx.copy_stream(compressed, decompressed)
    
    logger.success(f"✅ Decompressed to {output_csv_path}")
    return output_csv_path


def load_databento_csv(csv_path: Path, symbol: str) -> pd.DataFrame:
    """
    Load Databento CSV and convert to our schema.
    
    Databento OHLCV-1m schema typically includes:
    - ts_event: timestamp in nanoseconds
    - symbol: contract code
    - open, high, low, close: prices
    - volume: trade volume
    """
    logger.info(f"Loading CSV for {symbol}...")
    
    # Read CSV (Databento CSVs have headers)
    df = pd.read_csv(csv_path)
    
    logger.info(f"Loaded {len(df):,} rows, columns: {df.columns.tolist()}")
    
    # Convert timestamp (Databento uses nanosecond timestamps)
    if 'ts_event' in df.columns:
        df['timestamp'] = pd.to_datetime(df['ts_event'], unit='ns', utc=True)
    else:
        raise ValueError(f"Expected 'ts_event' column in Databento CSV")
    
    # Rename columns to match our schema
    df = df.rename(columns={
        'symbol': 'contract',  # Keep contract for filtering
    })
    
    # Keep only required columns
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'contract']
    df = df[required_cols].copy()
    
    # Remove any rows with NaN prices
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    
    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    logger.info(f"Processed {len(df):,} bars from {df['timestamp'].min()} to {df['timestamp'].max()}")
    logger.info(f"Unique contracts: {df['contract'].nunique()}")
    logger.info(f"Contract samples: {df['contract'].unique()[:10].tolist()}")
    
    return df


def build_continuous_contract(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Build a continuous contract from individual futures contracts.
    
    For simplicity, we'll use a "front-month" approach:
    - At each point in time, use the contract with the highest volume
    - This naturally rolls to the next contract as expiry approaches
    - IMPORTANT: Filter out calendar spreads (contracts with '-' in the name)
    
    Alternative: Could use specific roll dates (e.g., 5 days before expiry)
    """
    logger.info(f"Building continuous contract for {symbol}...")
    
    # Filter out calendar spreads (they have '-' in the contract name)
    # Spreads have prices like -10, +5 which corrupts our data!
    logger.info(f"Total rows before filtering: {len(df):,}")
    df = df[~df['contract'].str.contains('-', na=False)].copy()
    logger.info(f"Total rows after removing spreads: {len(df):,}")
    
    # Group by timestamp and find the contract with max volume at each timestamp
    def get_front_month(group):
        """Select the row with highest volume (front month contract)."""
        if len(group) == 0:
            return None
        return group.loc[group['volume'].idxmax()]
    
    continuous_df = df.groupby('timestamp', as_index=False).apply(get_front_month)
    continuous_df = continuous_df.reset_index(drop=True)
    
    # Drop the contract column as we now have a continuous series
    continuous_df = continuous_df.drop(columns=['contract'])
    
    logger.success(f"✅ Built continuous contract: {len(continuous_df):,} bars")
    
    return continuous_df


def convert_to_json_format(df: pd.DataFrame, symbol: str, interval: str = '1m') -> dict:
    """
    Convert DataFrame to our JSON format.
    
    Expected output structure:
    {
        "symbol": "ES",
        "display_name": "E-mini S&P 500",
        "interval": "1m",
        "start_date": "2020-10-06T00:00:00",
        "end_date": "2025-10-05T23:59:00",
        "bar_count": 1234567,
        "data": [
            {"timestamp": "2020-10-06 09:30:00", "open": 3400.0, ...},
            ...
        ]
    }
    """
    display_names = {
        'ES': 'E-mini S&P 500',
        'NQ': 'Micro E-mini Nasdaq',
        'GC': 'Gold Futures',
        '6E': 'Euro FX Futures'
    }
    
    # Convert timestamp to string format
    df_copy = df.copy()
    df_copy['timestamp'] = df_copy['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    data_dict = {
        'symbol': symbol,
        'display_name': display_names.get(symbol, symbol),
        'interval': interval,
        'start_date': df['timestamp'].min().isoformat(),
        'end_date': df['timestamp'].max().isoformat(),
        'bar_count': len(df),
        'data_source': 'Databento',
        'continuous_contract': True,
        'data': df_copy.to_dict(orient='records')
    }
    
    return data_dict


def process_instrument(symbol: str, input_dir: Path, output_dir: Path):
    """Process a single instrument from Databento data to JSON."""
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Processing {symbol}")
    logger.info(f"{'='*80}")
    
    # Get the Databento folder
    folder_name = DATABENTO_FOLDERS.get(symbol)
    if not folder_name:
        logger.error(f"No Databento folder mapping for {symbol}")
        return
    
    databento_dir = input_dir / folder_name
    if not databento_dir.exists():
        logger.error(f"Databento directory not found: {databento_dir}")
        return
    
    # Find the CSV.zst file
    zst_files = list(databento_dir.glob("*.csv.zst"))
    if not zst_files:
        logger.error(f"No CSV.zst file found in {databento_dir}")
        return
    
    zst_path = zst_files[0]
    logger.info(f"Found compressed file: {zst_path.name}")
    logger.info(f"File size: {zst_path.stat().st_size / (1024**2):.1f} MB")
    
    # Create temp directory for decompression
    temp_dir = input_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    csv_path = temp_dir / f"{symbol}_decompressed.csv"
    
    # Decompress
    decompress_zst_file(zst_path, csv_path)
    
    try:
        csv_size_mb = csv_path.stat().st_size / (1024**2)
        logger.info(f"Decompressed CSV size: {csv_size_mb:.1f} MB")
        
        # Load and process
        df = load_databento_csv(csv_path, symbol)
        
        # Build continuous contract
        continuous_df = build_continuous_contract(df, symbol)
        
        # Convert to JSON
        json_data = convert_to_json_format(continuous_df, symbol)
        
        # Save
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{symbol}_1m.json"
        
        logger.info(f"Saving to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        output_size_mb = output_file.stat().st_size / (1024**2)
        logger.success(f"✅ Saved {symbol}: {json_data['bar_count']:,} bars ({output_size_mb:.1f} MB)")
        
        # Print sample data
        logger.info(f"\nSample data (first 3 bars):")
        for i, bar in enumerate(json_data['data'][:3]):
            logger.info(f"  {i+1}. {bar['timestamp']} | O:{bar['open']:.2f} H:{bar['high']:.2f} L:{bar['low']:.2f} C:{bar['close']:.2f} V:{bar['volume']}")
        
        logger.info(f"\nPrice range: ${continuous_df['close'].min():.2f} - ${continuous_df['close'].max():.2f}")
        logger.info(f"Date range: {json_data['start_date'][:10]} to {json_data['end_date'][:10]}")
        
    finally:
        # Clean up temp file
        if csv_path.exists():
            csv_path.unlink()
            logger.info(f"Cleaned up temp file: {csv_path.name}")


def main():
    """Main conversion workflow."""
    
    # Setup logging
    logger.remove()
    logger.add(sys.stdout, level="INFO", 
              format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
    
    # Paths
    input_dir = Path("data_cache")
    output_dir = Path("data_cache/databento_1m")
    
    logger.info("="*80)
    logger.info("DATABENTO TO JSON CONVERTER")
    logger.info("="*80)
    logger.info(f"Input directory: {input_dir.absolute()}")
    logger.info(f"Output directory: {output_dir.absolute()}")
    
    # Process each instrument
    instruments = ['ES', 'NQ', 'GC', '6E']
    
    for symbol in instruments:
        try:
            process_instrument(symbol, input_dir, output_dir)
        except Exception as e:
            logger.error(f"Failed to process {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info("\n" + "="*80)
    logger.success("✅ CONVERSION COMPLETE")
    logger.info("="*80)
    logger.info(f"Output files saved to: {output_dir.absolute()}")
    logger.info("\nNext steps:")
    logger.info("1. Update backtest config to use data_cache/databento_1m")
    logger.info("2. Run: python scripts/run_multi_instrument_backtest.py")


if __name__ == "__main__":
    main()
