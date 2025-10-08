"""Yahoo Finance data provider implementation."""

from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from loguru import logger

from .base import DataProvider


class YahooProvider(DataProvider):
    """Yahoo Finance data provider for free equity/ETF data.

    Uses yfinance library to fetch historical minute bars. Note that Yahoo
    intraday history is limited to ~30 days for 1-minute bars.
    """

    def __init__(self) -> None:
        """Initialize Yahoo Finance provider."""
        self._interval_map = {
            "1m": "1m",
            "2m": "2m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1d": "1d",
        }

    @property
    def name(self) -> str:
        """Provider name."""
        return "yahoo"

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from Yahoo Finance.

        Args:
            symbol: Ticker symbol (e.g., 'SPY', 'QQQ').
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval (1m, 5m, 15m, 30m, 1h, 1d).

        Returns:
            DataFrame with standardized schema.

        Raises:
            ValueError: If interval is unsupported or date range invalid.
            RuntimeError: If data fetch fails.
        """
        if interval not in self._interval_map:
            raise ValueError(
                f"Unsupported interval: {interval}. Must be one of {list(self._interval_map.keys())}"
            )

        if start >= end:
            raise ValueError(f"start ({start}) must be before end ({end})")

        logger.info(f"Fetching {symbol} from Yahoo Finance: {start} to {end}, interval={interval}")

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start,
                end=end,
                interval=self._interval_map[interval],
                auto_adjust=False,
                actions=False,
            )
        except Exception as e:
            raise RuntimeError(f"Yahoo Finance fetch failed for {symbol}: {e}") from e

        if df.empty:
            logger.warning(f"No data returned from Yahoo Finance for {symbol}")
            return self._empty_dataframe()

        # Normalize schema
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "timestamp",
            "Datetime": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        # Ensure UTC timezone
        if df["timestamp"].dt.tz is None:
            # Yahoo sometimes returns naive datetimes in US Eastern
            logger.debug(f"Converting naive timestamps to UTC for {symbol}")
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("US/Eastern")
        
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

        # Add metadata
        df["symbol"] = symbol
        df["source"] = self.name

        # Select required columns
        required_cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol", "source"]
        df = df[required_cols]

        # Set index
        df = df.set_index("timestamp").sort_index()

        logger.info(f"Fetched {len(df)} bars for {symbol}")

        return df

    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol exists on Yahoo Finance.

        Args:
            symbol: Ticker symbol.

        Returns:
            True if symbol is valid, False otherwise.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return bool(info and "symbol" in info)
        except Exception as e:
            logger.debug(f"Symbol validation failed for {symbol}: {e}")
            return False

    @staticmethod
    def _empty_dataframe() -> pd.DataFrame:
        """Return empty DataFrame with correct schema."""
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume", "symbol", "source"]
        ).set_index("timestamp")
