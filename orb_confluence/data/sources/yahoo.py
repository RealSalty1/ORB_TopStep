"""Yahoo Finance data provider with retry logic and rate limiting."""

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger


class YahooProvider:
    """Yahoo Finance data provider for free equity/ETF data.

    Features:
    - Exponential backoff retry logic
    - Rate limiting (respects Yahoo's limits)
    - Automatic timezone handling (converts to UTC)
    - Schema normalization
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        rate_limit_delay: float = 0.5,
    ) -> None:
        """Initialize Yahoo provider.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_retry_delay: Initial delay between retries (seconds).
            rate_limit_delay: Delay between requests to respect rate limits (seconds).
        """
        self.name = "yahoo"
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.rate_limit_delay = rate_limit_delay

        self._interval_map = {
            "1m": "1m",
            "2m": "2m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1d": "1d",
        }

    def fetch_intraday(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV bars from Yahoo Finance.

        Args:
            symbol: Ticker symbol (e.g., 'SPY', 'QQQ').
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval (1m, 5m, 15m, 30m, 1h, 1d).

        Returns:
            DataFrame with columns: timestamp_utc, open, high, low, close, volume, symbol, source.
            Empty DataFrame if no data available.

        Raises:
            ValueError: If interval is unsupported.
            RuntimeError: If fetch fails after all retries.
        """
        if interval not in self._interval_map:
            raise ValueError(
                f"Unsupported interval: {interval}. Must be one of {list(self._interval_map.keys())}"
            )

        logger.info(f"Fetching {symbol} from Yahoo: {start} to {end}, interval={interval}")

        # Retry loop with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                if attempt > 0:
                    time.sleep(self.rate_limit_delay)

                df = self._fetch_with_yfinance(symbol, start, end, interval)

                if df.empty:
                    logger.warning(f"No data returned for {symbol}")
                    return self._empty_dataframe()

                # Normalize schema
                df = self._normalize_schema(df, symbol)

                logger.info(f"Fetched {len(df)} bars for {symbol}")
                return df

            except Exception as e:
                retry_delay = self.initial_retry_delay * (2**attempt)

                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Yahoo fetch failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {retry_delay:.1f}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Yahoo fetch failed after {self.max_retries} attempts: {e}")
                    raise RuntimeError(f"Yahoo Finance fetch failed for {symbol}: {e}") from e

        return self._empty_dataframe()

    def _fetch_with_yfinance(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> pd.DataFrame:
        """Internal fetch using yfinance library.

        Args:
            symbol: Ticker symbol.
            start: Start datetime.
            end: End datetime.
            interval: Interval string.

        Returns:
            Raw DataFrame from yfinance.
        """
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start,
            end=end,
            interval=self._interval_map[interval],
            auto_adjust=False,
            actions=False,
        )
        return df

    def _normalize_schema(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Normalize DataFrame to standard schema.

        Args:
            df: Raw DataFrame from yfinance.
            symbol: Symbol string.

        Returns:
            Normalized DataFrame with standard columns.
        """
        df = df.reset_index()
        df = df.rename(columns=str.lower)

        # Handle different timestamp column names
        if "datetime" in df.columns:
            df["timestamp_utc"] = pd.to_datetime(df["datetime"], utc=True)
        elif "date" in df.columns:
            df["timestamp_utc"] = pd.to_datetime(df["date"], utc=True)
        else:
            raise ValueError("No recognized timestamp column in yfinance data")

        # Ensure UTC timezone
        if df["timestamp_utc"].dt.tz is None:
            # Yahoo sometimes returns naive timestamps (US/Eastern)
            logger.debug(f"Converting naive timestamps to UTC for {symbol}")
            df["timestamp_utc"] = df["timestamp_utc"].dt.tz_localize("US/Eastern")

        df["timestamp_utc"] = df["timestamp_utc"].dt.tz_convert("UTC")

        # Add metadata
        df["symbol"] = symbol
        df["source"] = self.name

        # Select and order columns
        return df[["timestamp_utc", "open", "high", "low", "close", "volume", "symbol", "source"]]

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """Return empty DataFrame with correct schema."""
        return pd.DataFrame(
            columns=["timestamp_utc", "open", "high", "low", "close", "volume", "symbol", "source"]
        )