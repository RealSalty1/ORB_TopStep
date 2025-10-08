"""Data manager for coordinating data access and caching."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from loguru import logger

from ..config import InstrumentConfig
from .base import DataProvider
from .binance_provider import BinanceProvider
from .synthetic_provider import SyntheticProvider
from .yahoo_provider import YahooProvider


class DataManager:
    """Coordinates data access across multiple providers with caching.

    Provides unified interface to fetch data from appropriate provider based
    on instrument configuration. Handles local caching in Parquet format.
    """

    def __init__(
        self,
        cache_dir: Path = Path("data/cache"),
        enable_cache: bool = True,
    ) -> None:
        """Initialize data manager.

        Args:
            cache_dir: Directory for cached data.
            enable_cache: Whether to use local caching.
        """
        self.cache_dir = cache_dir
        self.enable_cache = enable_cache

        if enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize providers
        self._providers: Dict[str, DataProvider] = {
            "yahoo": YahooProvider(),
            "binance": BinanceProvider(),
            "synthetic": SyntheticProvider(),
        }

    def fetch_data(
        self,
        instrument: InstrumentConfig,
        start: datetime,
        end: datetime,
        interval: str = "1m",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Fetch data for an instrument.

        Args:
            instrument: Instrument configuration.
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval.
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            DataFrame with OHLCV data.

        Raises:
            ValueError: If data source is unsupported.
            RuntimeError: If data fetch fails.
        """
        symbol = instrument.proxy_symbol
        source = instrument.data_source

        logger.info(
            f"Fetching data for {symbol} ({instrument.symbol}) from {source}: "
            f"{start} to {end}, interval={interval}"
        )

        # Check cache first
        if self.enable_cache and not force_refresh:
            cached_df = self._load_from_cache(symbol, start, end, interval)
            if cached_df is not None:
                logger.info(f"Loaded {len(cached_df)} bars from cache for {symbol}")
                return cached_df

        # Fetch from provider
        provider = self._get_provider(source)
        df = provider.fetch_bars(
            symbol=symbol,
            start=start,
            end=end,
            interval=interval,
        )

        # Update metadata
        df["symbol"] = instrument.symbol  # Use target symbol, not proxy
        df["proxy_symbol"] = symbol
        df["source"] = source

        # Save to cache
        if self.enable_cache and not df.empty:
            self._save_to_cache(df, symbol, interval)

        return df

    def _get_provider(self, source: str) -> DataProvider:
        """Get provider instance by name.

        Args:
            source: Provider name ('yahoo', 'binance', 'synthetic').

        Returns:
            Provider instance.

        Raises:
            ValueError: If provider is not available.
        """
        if source not in self._providers:
            raise ValueError(
                f"Unsupported data source: {source}. "
                f"Available: {list(self._providers.keys())}"
            )
        return self._providers[source]

    def _cache_path(self, symbol: str, interval: str) -> Path:
        """Get cache file path for symbol and interval.

        Args:
            symbol: Symbol.
            interval: Interval.

        Returns:
            Path to cache file.
        """
        return self.cache_dir / f"{symbol}_{interval}.parquet"

    def _load_from_cache(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> Optional[pd.DataFrame]:
        """Load data from cache if available.

        Args:
            symbol: Symbol.
            start: Start datetime.
            end: End datetime.
            interval: Interval.

        Returns:
            Cached DataFrame or None if not available.
        """
        cache_path = self._cache_path(symbol, interval)

        if not cache_path.exists():
            return None

        try:
            df = pd.read_parquet(cache_path)
            
            # Ensure index is datetime
            if not isinstance(df.index, pd.DatetimeIndex):
                df = df.set_index("timestamp")

            # Filter to requested range
            df = df[(df.index >= start) & (df.index < end)]

            # Check if we have complete coverage
            expected_bars = (end - start).total_seconds() / 60  # Assuming 1m
            coverage = len(df) / expected_bars if expected_bars > 0 else 0

            if coverage < 0.95:  # Require 95% coverage
                logger.debug(
                    f"Insufficient cache coverage for {symbol} "
                    f"({coverage:.1%}), will fetch fresh data"
                )
                return None

            return df

        except Exception as e:
            logger.warning(f"Failed to load cache for {symbol}: {e}")
            return None

    def _save_to_cache(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
    ) -> None:
        """Save data to cache.

        Args:
            df: DataFrame to cache.
            symbol: Symbol.
            interval: Interval.
        """
        cache_path = self._cache_path(symbol, interval)

        try:
            # Load existing cache if present
            if cache_path.exists():
                existing = pd.read_parquet(cache_path)
                if not isinstance(existing.index, pd.DatetimeIndex):
                    existing = existing.set_index("timestamp")

                # Merge with new data (new data takes precedence)
                df = pd.concat([existing, df])
                df = df[~df.index.duplicated(keep="last")]
                df = df.sort_index()

            # Save
            df.to_parquet(cache_path, compression="snappy")
            logger.debug(f"Saved {len(df)} bars to cache for {symbol}")

        except Exception as e:
            logger.warning(f"Failed to save cache for {symbol}: {e}")
