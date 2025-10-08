"""Binance data provider with retry logic and rate limiting."""

import time
from datetime import datetime, timezone
from typing import Any, List

import pandas as pd
import requests
from loguru import logger


class BinanceProvider:
    """Binance data provider for free cryptocurrency data.

    Features:
    - Exponential backoff retry logic
    - Rate limiting (respects Binance weight limits)
    - Batching for large date ranges
    - Automatic UTC timezone handling
    """

    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        rate_limit_delay: float = 0.2,
    ) -> None:
        """Initialize Binance provider.

        Args:
            base_url: Binance API base URL.
            max_retries: Maximum number of retry attempts.
            initial_retry_delay: Initial delay between retries (seconds).
            rate_limit_delay: Delay between requests (seconds).
        """
        self.base_url = base_url
        self.name = "binance"
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.rate_limit_delay = rate_limit_delay

        self._interval_map = {
            "1m": "1m",
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
        """Fetch intraday OHLCV bars from Binance.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT', 'ETHUSDT').
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

        logger.info(f"Fetching {symbol} from Binance: {start} to {end}, interval={interval}")

        # Convert to millisecond timestamps
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        # Fetch with batching (Binance limits to 1000 bars per request)
        all_klines: List[List[Any]] = []
        current_start = start_ms
        limit = 1000

        while current_start < end_ms:
            # Retry loop for each batch
            for attempt in range(self.max_retries):
                try:
                    # Rate limiting
                    time.sleep(self.rate_limit_delay)

                    klines = self._fetch_klines(
                        symbol=symbol,
                        interval=self._interval_map[interval],
                        start_time=current_start,
                        end_time=end_ms,
                        limit=limit,
                    )

                    if not klines:
                        logger.debug(f"No more data available for {symbol} from {current_start}")
                        break

                    all_klines.extend(klines)

                    # Update start time for next batch (last kline close time + 1)
                    current_start = klines[-1][6] + 1

                    if len(klines) < limit:
                        # Received fewer than limit, no more data available
                        break

                    # Success, break retry loop
                    break

                except Exception as e:
                    retry_delay = self.initial_retry_delay * (2**attempt)

                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"Binance fetch failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                            f"Retrying in {retry_delay:.1f}s..."
                        )
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"Binance fetch failed after {self.max_retries} attempts: {e}")
                        raise RuntimeError(f"Binance API request failed for {symbol}: {e}") from e

        if not all_klines:
            logger.warning(f"No data returned for {symbol}")
            return self._empty_dataframe()

        # Convert to DataFrame and normalize
        df = self._normalize_klines(all_klines, symbol, start, end)

        logger.info(f"Fetched {len(df)} bars for {symbol}")
        return df

    def _fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> List[List[Any]]:
        """Fetch klines from Binance API.

        Args:
            symbol: Trading pair.
            interval: Interval string (Binance format).
            start_time: Start time (milliseconds).
            end_time: End time (milliseconds).
            limit: Maximum number of bars per request.

        Returns:
            List of kline data arrays.

        Raises:
            requests.HTTPError: If request fails.
        """
        endpoint = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }

        response = requests.get(endpoint, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def _normalize_klines(
        self,
        klines: List[List[Any]],
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Normalize klines to standard schema.

        Args:
            klines: Raw klines from Binance.
            symbol: Symbol string.
            start: Start datetime for filtering.
            end: End datetime for filtering.

        Returns:
            Normalized DataFrame.
        """
        df = pd.DataFrame(
            klines,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )

        # Convert timestamps (milliseconds to datetime)
        df["timestamp_utc"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

        # Convert prices and volume to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Add metadata
        df["symbol"] = symbol
        df["source"] = self.name

        # Filter to exact time range
        df = df[(df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]

        # Select and order columns
        return df[["timestamp_utc", "open", "high", "low", "close", "volume", "symbol", "source"]]

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """Return empty DataFrame with correct schema."""
        return pd.DataFrame(
            columns=["timestamp_utc", "open", "high", "low", "close", "volume", "symbol", "source"]
        )