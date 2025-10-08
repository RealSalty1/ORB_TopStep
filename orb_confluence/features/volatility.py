"""Volatility calculations (ATR, normalized volatility)."""

import numpy as np
import pandas as pd
from numba import jit


@jit(nopython=True)
def _true_range_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Calculate True Range using numba."""
    n = len(high)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]

    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    return tr


@jit(nopython=True)
def _wilder_smooth_numba(values: np.ndarray, period: int) -> np.ndarray:
    """Apply Wilder's smoothing using numba."""
    n = len(values)
    smoothed = np.zeros(n)

    if n >= period:
        smoothed[period - 1] = np.mean(values[:period])
        for i in range(period, n):
            smoothed[i] = (smoothed[i - 1] * (period - 1) + values[i]) / period
    else:
        smoothed[:] = np.nan

    smoothed[: period - 1] = np.nan
    return smoothed


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range.

    Args:
        df: DataFrame with high, low, close columns.
        period: ATR period.

    Returns:
        Series of ATR values.
    """
    # TODO: Add validation and edge case handling
    tr = _true_range_numba(df["high"].values, df["low"].values, df["close"].values)
    atr = _wilder_smooth_numba(tr, period)
    return pd.Series(atr, index=df.index, name="ATR")


def compute_normalized_volatility(
    df: pd.DataFrame, intraday_period: int = 14, daily_window: int = 14
) -> float:
    """Compute normalized volatility (intraday ATR / daily ATR proxy).

    Args:
        df: DataFrame with OHLC data.
        intraday_period: Period for intraday ATR.
        daily_window: Window for daily range estimation.

    Returns:
        Normalized volatility ratio.
    """
    # TODO: Implement proper normalized volatility calculation
    atr_intraday = compute_atr(df, period=intraday_period).iloc[-1]
    daily_range = df["high"].iloc[-daily_window:].max() - df["low"].iloc[-daily_window:].min()

    if daily_range == 0:
        return 0.0

    return atr_intraday / daily_range
