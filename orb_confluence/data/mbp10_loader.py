"""
MBP-10 Data Loader

Loads and parses Market By Price Level 10 data from Databento CSV.ZST files.
Provides fast access to order book snapshots for backtesting and live trading.

Author: Nick Burner
Date: October 9, 2025
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import zstandard as zstd
from io import StringIO
from loguru import logger


class MBP10Loader:
    """
    Load and parse MBP-10 (Market By Price Level 10) order book data.
    
    Features:
    - Decompress .zst files on-the-fly
    - Fast timestamp-based lookups
    - Memory-efficient chunked loading
    - Caching for repeated queries
    
    Usage:
        loader = MBP10Loader(data_directory="data_cache/GLBX-20251008-HHT7VXJSSJ")
        
        # Get snapshot at specific time
        snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
        
        # Get time series of OFI
        ofi_series = loader.get_ofi_series(
            start="2025-09-15 09:30:00",
            end="2025-09-15 16:00:00"
        )
    """
    
    def __init__(self, data_directory: str):
        """
        Initialize MBP10Loader.
        
        Args:
            data_directory: Directory containing .mbp-10.csv.zst files
        """
        self.data_dir = Path(data_directory)
        
        if not self.data_dir.exists():
            raise ValueError(f"Data directory not found: {data_directory}")
        
        # Cache for loaded data (date -> DataFrame)
        self._cache: Dict[str, pd.DataFrame] = {}
        
        # Max cache size (number of days)
        self._max_cache_size = 3
        
        logger.info(f"MBP10Loader initialized with directory: {self.data_dir}")
    
    def _decompress_zst_file(self, file_path: Path) -> str:
        """
        Decompress a .zst file and return contents as string.
        
        Args:
            file_path: Path to .zst file
            
        Returns:
            Decompressed CSV data as string
        """
        logger.debug(f"Decompressing {file_path.name}...")
        
        with open(file_path, 'rb') as compressed:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(compressed) as reader:
                return reader.read().decode('utf-8')
    
    def _load_date(self, date: str) -> pd.DataFrame:
        """
        Load MBP-10 data for a specific date.
        
        Args:
            date: Date string (YYYYMMDD or YYYY-MM-DD)
            
        Returns:
            DataFrame with MBP-10 data
        """
        # Normalize date format
        if '-' in date:
            date = date.replace('-', '')
        
        # Check cache first
        if date in self._cache:
            logger.debug(f"Returning cached data for {date}")
            return self._cache[date]
        
        # Find file
        file_path = self.data_dir / f"glbx-mdp3-{date}.mbp-10.csv.zst"
        
        if not file_path.exists():
            raise FileNotFoundError(f"MBP-10 file not found: {file_path}")
        
        logger.info(f"Loading MBP-10 data from {file_path.name}...")
        
        # Decompress and parse
        csv_data = self._decompress_zst_file(file_path)
        
        # Parse CSV
        df = pd.read_csv(StringIO(csv_data))
        
        # Parse timestamps
        df['ts_event'] = pd.to_datetime(df['ts_event'])
        df['ts_recv'] = pd.to_datetime(df['ts_recv'])
        
        # Sort by ts_event but don't set as index (duplicates exist)
        df = df.sort_values('ts_event').reset_index(drop=True)
        
        logger.info(f"Loaded {len(df):,} order book updates for {date}")
        
        # Add to cache
        self._cache[date] = df
        
        # Limit cache size
        if len(self._cache) > self._max_cache_size:
            # Remove oldest
            oldest_date = min(self._cache.keys())
            logger.debug(f"Cache full, removing {oldest_date}")
            del self._cache[oldest_date]
        
        return df
    
    def get_snapshot_at(
        self,
        date: str,
        time: str,
        tolerance_seconds: int = 5
    ) -> Optional[Dict]:
        """
        Get order book snapshot at specific timestamp.
        
        Args:
            date: Date string (YYYYMMDD or YYYY-MM-DD)
            time: Time string (HH:MM:SS) or full datetime string
            tolerance_seconds: Max seconds to look back/forward for data
            
        Returns:
            Dictionary with order book levels or None if not found
            
        Example:
            snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
            print(snapshot['bid_px_00'])  # Best bid price
            print(snapshot['ask_px_00'])  # Best ask price
        """
        # Parse timestamp
        if isinstance(time, str) and ':' in time:
            # Combine date and time
            if len(time.split(':')) == 2:
                time += ':00'  # Add seconds if missing
            timestamp_str = f"{date} {time}"
        else:
            timestamp_str = f"{date} {time}"
        
        timestamp = pd.Timestamp(timestamp_str, tz='UTC')  # Make timezone-aware
        
        # Load data for this date
        try:
            df = self._load_date(date)
        except FileNotFoundError:
            logger.warning(f"No data found for date {date}")
            return None
        
        # Find nearest timestamp within tolerance
        tolerance = pd.Timedelta(seconds=tolerance_seconds)
        
        # Find closest timestamp
        time_diffs = (df['ts_event'] - timestamp).abs()
        idx = time_diffs.idxmin()
        
        if idx < 0 or idx >= len(df):
            logger.warning(f"No data found near {timestamp}")
            return None
        
        closest_time = df.loc[idx, 'ts_event']
        
        # Check tolerance
        if abs(closest_time - timestamp) > tolerance:
            logger.warning(f"Closest data at {closest_time} exceeds tolerance of {tolerance_seconds}s")
            return None
        
        # Return as dictionary
        return df.iloc[idx].to_dict()
    
    def get_range(
        self,
        start: str,
        end: str,
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get order book data for a time range.
        
        Args:
            start: Start timestamp (YYYY-MM-DD HH:MM:SS)
            end: End timestamp (YYYY-MM-DD HH:MM:SS)
            columns: Specific columns to return (None = all)
            
        Returns:
            DataFrame with order book snapshots
            
        Example:
            # Get all data from 9:30-16:00 on Sept 15
            df = loader.get_range(
                start="2025-09-15 09:30:00",
                end="2025-09-15 16:00:00"
            )
        """
        start_ts = pd.Timestamp(start, tz='UTC')
        end_ts = pd.Timestamp(end, tz='UTC')
        
        # Determine dates to load
        current_date = start_ts.date()
        end_date = end_ts.date()
        
        dfs = []
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y%m%d')
            
            try:
                df = self._load_date(date_str)
                
                # Filter by time range
                mask = (df['ts_event'] >= start_ts) & (df['ts_event'] <= end_ts)
                df_filtered = df[mask]
                
                if len(df_filtered) > 0:
                    dfs.append(df_filtered)
                
            except FileNotFoundError:
                logger.warning(f"No data for {date_str}")
            
            # Next day
            current_date += timedelta(days=1)
        
        if len(dfs) == 0:
            logger.warning(f"No data found in range {start} to {end}")
            return pd.DataFrame()
        
        # Concatenate
        result = pd.concat(dfs)
        
        # Filter columns if specified
        if columns is not None:
            missing_cols = set(columns) - set(result.columns)
            if missing_cols:
                logger.warning(f"Columns not found: {missing_cols}")
            result = result[[c for c in columns if c in result.columns]]
        
        logger.info(f"Loaded {len(result):,} updates from {start} to {end}")
        
        return result
    
    def get_ofi_series(
        self,
        start: str,
        end: str,
        level: int = 0
    ) -> pd.Series:
        """
        Get Order Flow Imbalance time series.
        
        Args:
            start: Start timestamp
            end: End timestamp
            level: Book level (0 = best, 9 = 10th level)
            
        Returns:
            Series of OFI values indexed by timestamp
        """
        # Get bid/ask size columns
        bid_col = f'bid_sz_{level:02d}'
        ask_col = f'ask_sz_{level:02d}'
        
        # Load data
        df = self.get_range(start, end, columns=[bid_col, ask_col])
        
        if df.empty:
            return pd.Series()
        
        # Calculate OFI
        ofi = (df[bid_col] - df[ask_col]) / (df[bid_col] + df[ask_col])
        
        return ofi
    
    def get_depth_imbalance_series(
        self,
        start: str,
        end: str,
        levels: int = 10
    ) -> pd.Series:
        """
        Get Depth Imbalance time series (sum of all levels).
        
        Args:
            start: Start timestamp
            end: End timestamp
            levels: Number of levels to sum (1-10)
            
        Returns:
            Series of depth imbalance values
        """
        # Get all bid/ask columns
        columns = []
        for level in range(levels):
            columns.extend([f'bid_sz_{level:02d}', f'ask_sz_{level:02d}'])
        
        # Load data
        df = self.get_range(start, end, columns=columns)
        
        if df.empty:
            return pd.Series()
        
        # Sum bids and asks
        total_bid = sum(df[f'bid_sz_{i:02d}'] for i in range(levels))
        total_ask = sum(df[f'ask_sz_{i:02d}'] for i in range(levels))
        
        # Calculate depth imbalance
        depth_imb = (total_bid - total_ask) / (total_bid + total_ask)
        
        return depth_imb
    
    def clear_cache(self):
        """Clear the data cache."""
        logger.info(f"Clearing cache ({len(self._cache)} dates)")
        self._cache.clear()
    
    def __repr__(self):
        return f"MBP10Loader(data_dir={self.data_dir}, cached_dates={len(self._cache)})"


if __name__ == "__main__":
    # Demo usage
    loader = MBP10Loader(data_directory="data_cache/GLBX-20251008-HHT7VXJSSJ")
    
    # Get snapshot
    snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
    if snapshot:
        print(f"Best bid: ${snapshot['bid_px_00']:.2f} x {snapshot['bid_sz_00']}")
        print(f"Best ask: ${snapshot['ask_px_00']:.2f} x {snapshot['ask_sz_00']}")
    
    # Get OFI series
    ofi = loader.get_ofi_series(
        start="2025-09-15 09:30:00",
        end="2025-09-15 10:00:00"
    )
    print(f"\nOFI mean: {ofi.mean():.4f}")
    print(f"OFI std: {ofi.std():.4f}")

