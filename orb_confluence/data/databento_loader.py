"""Databento data loader for ORB 2.0 backtesting.

Loads professional futures data from Databento JSON files.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from loguru import logger


class DatabentoLoader:
    """Loads Databento 1-minute OHLCV data.
    
    Example:
        >>> loader = DatabentoLoader("data_cache/databento_1m")
        >>> bars = loader.load("ES", start_date="2025-01-01", end_date="2025-10-07")
        >>> print(f"Loaded {len(bars)} bars")
    """
    
    def __init__(self, data_directory: str):
        """Initialize loader.
        
        Args:
            data_directory: Directory containing Databento JSON files
        """
        self.data_dir = Path(data_directory)
        if not self.data_dir.exists():
            raise ValueError(f"Data directory not found: {data_directory}")
    
    def load(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load bars for symbol.
        
        Args:
            symbol: Instrument symbol (ES, NQ, GC, 6E)
            start_date: Start date (YYYY-MM-DD), None = all
            end_date: End date (YYYY-MM-DD), None = all
            
        Returns:
            DataFrame with columns: timestamp_utc, open, high, low, close, volume
        """
        file_path = self.data_dir / f"{symbol}_1m.json"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")
        
        logger.info(f"Loading {symbol} from {file_path} ({file_path.stat().st_size / 1024 / 1024:.1f} MB)")
        
        # Load JSON
        with open(file_path, 'r') as f:
            json_data = json.load(f)
        
        # Extract metadata
        logger.info(f"Metadata: {json_data['symbol']}, {json_data['bar_count']} bars, {json_data['start_date']} to {json_data['end_date']}")
        
        # Get data array
        data_array = json_data.get('data', [])
        
        if not data_array:
            logger.error(f"No data found in {file_path}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        records = []
        for record in data_array:
            # Parse timestamp string
            ts_str = record['timestamp']
            ts = pd.Timestamp(ts_str, tz='UTC')
            
            records.append({
                'timestamp_utc': ts,
                'open': float(record['open']),
                'high': float(record['high']),
                'low': float(record['low']),
                'close': float(record['close']),
                'volume': int(record['volume']),
            })
        
        df = pd.DataFrame(records)
        
        # Sort by timestamp
        df = df.sort_values('timestamp_utc').reset_index(drop=True)
        
        logger.info(f"Loaded {len(df)} total bars")
        
        # Filter by date range
        if start_date:
            start_dt = pd.Timestamp(start_date, tz='UTC')
            df = df[df['timestamp_utc'] >= start_dt]
            logger.info(f"Filtered to {len(df)} bars after {start_date}")
        
        if end_date:
            end_dt = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
            df = df[df['timestamp_utc'] < end_dt]
            logger.info(f"Filtered to {len(df)} bars before {end_date}")
        
        if len(df) == 0:
            logger.warning(f"No data for {symbol} in date range {start_date} to {end_date}")
            return df
        
        logger.info(
            f"Final dataset: {len(df)} bars from {df['timestamp_utc'].min()} to {df['timestamp_utc'].max()}"
        )
        
        return df
    
    def available_symbols(self) -> list:
        """Get list of available symbols.
        
        Returns:
            List of symbol strings
        """
        json_files = list(self.data_dir.glob("*_1m.json"))
        symbols = [f.stem.replace("_1m", "") for f in json_files]
        return sorted(symbols)
    
    def get_date_range(self, symbol: str) -> tuple:
        """Get available date range for symbol.
        
        Args:
            symbol: Instrument symbol
            
        Returns:
            Tuple of (start_date, end_date) as strings
        """
        df = self.load(symbol)
        if len(df) == 0:
            return (None, None)
        
        start = df['timestamp_utc'].min().strftime('%Y-%m-%d')
        end = df['timestamp_utc'].max().strftime('%Y-%m-%d')
        
        return (start, end)

