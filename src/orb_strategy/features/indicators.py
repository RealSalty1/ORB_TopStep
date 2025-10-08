"""Core technical indicators implemented from scratch.

Manual implementations for ATR and related indicators to avoid external
dependencies and ensure full control over calculations.
"""

from typing import Optional

import numpy as np
import pandas as pd
from numba import jit


class ATR:
    """Average True Range indicator.

    Uses Wilder's smoothing method (exponential moving average variant).
    """

    def __init__(self, period: int = 14) -> None:
        """Initialize ATR indicator.

        Args:
            period: Lookback period for smoothing.

        Raises:
            ValueError: If period < 1.
        """
        if period < 1:
            raise ValueError(f"ATR period must be >= 1, got {period}")
        self.period = period

    def calculate(
        self,
        high: pd.Series | np.ndarray,
        low: pd.Series | np.ndarray,
        close: pd.Series | np.ndarray,
    ) -> pd.Series:
        """Calculate ATR.

        Args:
            high: High prices.
            low: Low prices.
            close: Close prices.

        Returns:
            Series of ATR values (same length as input).
        """
        # Convert to numpy for calculation
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
        close = np.asarray(close, dtype=float)

        if len(high) != len(low) or len(high) != len(close):
            raise ValueError("high, low, close must have same length")

        # Calculate True Range
        tr = self._true_range(high, low, close)

        # Apply Wilder's smoothing
        atr = self._wilder_smooth(tr, self.period)

        # Convert back to series if input was series
        if isinstance(high, pd.Series):
            return pd.Series(atr, index=high.index, name="ATR")
        
        return pd.Series(atr, name="ATR")

    @staticmethod
    @jit(nopython=True)
    def _true_range(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> np.ndarray:
        """Calculate True Range.

        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))

        Args:
            high: High prices.
            low: Low prices.
            close: Close prices.

        Returns:
            Array of TR values.
        """
        n = len(high)
        tr = np.zeros(n, dtype=np.float64)

        # First bar: just high - low
        tr[0] = high[0] - low[0]

        # Subsequent bars: consider previous close
        for i in range(1, n):
            hl = high[i] - low[i]
            hc = np.abs(high[i] - close[i - 1])
            lc = np.abs(low[i] - close[i - 1])
            tr[i] = max(hl, hc, lc)

        return tr

    @staticmethod
    @jit(nopython=True)
    def _wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
        """Apply Wilder's smoothing (RMA).

        RMA(i) = (RMA(i-1) * (period - 1) + value(i)) / period

        Args:
            values: Input values.
            period: Smoothing period.

        Returns:
            Smoothed array.
        """
        n = len(values)
        smoothed = np.zeros(n, dtype=np.float64)

        # Initialize with SMA for first period
        if n >= period:
            smoothed[period - 1] = np.mean(values[:period])

            # Apply Wilder's smoothing for rest
            for i in range(period, n):
                smoothed[i] = (smoothed[i - 1] * (period - 1) + values[i]) / period
        else:
            # Not enough data, return NaN
            smoothed[:] = np.nan

        # Set early values to NaN (not enough history)
        smoothed[: period - 1] = np.nan

        return smoothed


def compute_atr(
    df: pd.DataFrame,
    period: int = 14,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """Convenience function to compute ATR on DataFrame.

    Args:
        df: DataFrame with OHLC data.
        period: ATR period.
        high_col: Name of high column.
        low_col: Name of low column.
        close_col: Name of close column.

    Returns:
        Series of ATR values.
    """
    atr = ATR(period=period)
    return atr.calculate(
        high=df[high_col],
        low=df[low_col],
        close=df[close_col],
    )
