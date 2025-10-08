"""Base data provider interface and schemas."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

import pandas as pd
from pydantic import BaseModel, Field


class BarData(BaseModel):
    """Standardized OHLCV bar schema."""

    timestamp: datetime = Field(..., description="Bar open time (UTC)")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Closing price")
    volume: float = Field(..., description="Volume")
    symbol: str = Field(..., description="Instrument symbol")
    source: str = Field(..., description="Data source")

    class Config:
        """Pydantic config."""
        frozen = True
        arbitrary_types_allowed = True


class DataProvider(ABC):
    """Abstract base class for data providers.

    All data providers must implement this interface to ensure consistent
    data access patterns across different sources.
    """

    @abstractmethod
    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars for a symbol and time range.

        Args:
            symbol: Trading symbol.
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval (e.g., '1m', '5m', '1h', '1d').

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, symbol, source.
            Index is DatetimeIndex (UTC).

        Raises:
            ValueError: If parameters are invalid.
            RuntimeError: If data fetch fails.
        """
        pass

    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol is valid/available from this provider.

        Args:
            symbol: Trading symbol to validate.

        Returns:
            True if symbol is available, False otherwise.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass
