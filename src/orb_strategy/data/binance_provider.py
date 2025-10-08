"""Binance data provider implementation."""

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
import requests
from loguru import logger

from .base import DataProvider


class BinanceProvider(DataProvider):
    """Binance data provider for free cryptocurrency data.

    Uses Binance public REST API to fetch historical klines (candlesticks).
    No authentication required for historical data.
    """

    def __init__(self, base_url: str = "https://api.binance.com") -> None:
        """Initialize Binance provider.

        Args:
            base_url: Binance API base URL.
        """
        self.base_url = base_url
        self._interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1d": "1d",
        }

    @property
    def name(self) -> str:
        """Provider name."""
        return "binance"

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from Binance.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT', 'ETHUSDT').
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval (1m, 5m, 15m, 30m, 1h, 1d).

        Returns:
            DataFrame with standardized schema.

        Raises:
            ValueError: If interval is unsupported or parameters invalid.
            RuntimeError: If API request fails.
        """
        if interval not in self._interval_map:
            raise ValueError(
                f"Unsupported interval: {interval}. Must be one of {list(self._interval_map.keys())}"
            )

        if start >= end:
            raise ValueError(f"start ({start}) must be before end ({end})")

        logger.info(f"Fetching {symbol} from Binance: {start} to {end}, interval={interval}")

        # Convert to millisecond timestamps
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        # Binance API limits to 1000 bars per request
        all_klines: List[List[Any]] = []
        current_start = start_ms
        limit = 1000

        while current_start < end_ms:
            try:
                klines = self._fetch_klines(
                    symbol=symbol,
                    interval=self._interval_map[interval],
                    start_time=current_start,
                    end_time=end_ms,
                    limit=limit,
                )
            except Exception as e:
                raise RuntimeError(f"Binance API request failed for {symbol}: {e}") from e

            if not klines:
                break

            all_klines.extend(klines)
            
            # Update start time for next batch (last kline close time + 1)
            current_start = klines[-1][6] + 1

            if len(klines) < limit:
                break

        if not all_klines:
            logger.warning(f"No data returned from Binance for {symbol}")
            return self._empty_dataframe()

        # Convert to DataFrame
        df = pd.DataFrame(
            all_klines,
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

        # Convert timestamps
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

        # Convert prices and volume to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Add metadata
        df["symbol"] = symbol
        df["source"] = self.name

        # Select required columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol", "source"]
        df = df[required_cols]

        # Set index and filter to exact time range
        df = df.set_index("timestamp").sort_index()
        df = df[(df.index >= start) & (df.index < end)]

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
            limit: Maximum number of bars.

        Returns:
            List of kline data arrays.
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

    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol (trading pair) exists on Binance.

        Args:
            symbol: Trading pair symbol.

        Returns:
            True if symbol is valid, False otherwise.
        """
        try:
            endpoint = f"{self.base_url}/api/v3/exchangeInfo"
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            symbols = [s["symbol"] for s in data.get("symbols", [])]
            
            return symbol in symbols
        except Exception as e:
            logger.debug(f"Symbol validation failed for {symbol}: {e}")
            return False

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """Return empty DataFrame with correct schema."""
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume", "symbol", "source"]
        ).set_index("timestamp")
