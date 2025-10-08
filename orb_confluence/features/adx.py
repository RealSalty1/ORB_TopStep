"""Average Directional Index (ADX) calculation.

Manual implementation of ADX for trend strength measurement.
ADX values above threshold indicate strong trend, below indicates weak/choppy.
"""

from typing import Dict, Optional

import numpy as np
from loguru import logger


class ADX:
    """Average Directional Index calculator.

    Calculates ADX manually using True Range, +DI, -DI smoothing.

    ADX Interpretation:
    - ADX < 18-20: Weak trend (choppy, range-bound)
    - ADX > 18-20: Strong trend
    - ADX > 25: Very strong trend

    Example:
        >>> adx = ADX(period=14, threshold=18.0)
        >>> for bar in bars:
        ...     result = adx.update(bar['high'], bar['low'], bar['close'])
        ...     if result['usable']:
        ...         if result['trend_strong']:
        ...             print(f"Strong trend: ADX={result['adx_value']:.1f}")
    """

    def __init__(
        self,
        period: int = 14,
        threshold: float = 18.0,
    ) -> None:
        """Initialize ADX calculator.

        Args:
            period: Smoothing period (typically 14).
            threshold: ADX threshold for strong trend (typically 18-20).
        """
        self.period = period
        self.threshold = threshold

        # State
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []

        # Smoothed values (Wilder's smoothing)
        self._smoothed_tr: Optional[float] = None
        self._smoothed_plus_dm: Optional[float] = None
        self._smoothed_minus_dm: Optional[float] = None
        self._smoothed_dx: Optional[float] = None

    def update(self, high: float, low: float, close: float) -> Dict[str, float]:
        """Update ADX with new bar.

        Args:
            high: Bar high.
            low: Bar low.
            close: Bar close.

        Returns:
            Dictionary with:
            - adx_value: ADX value (or NaN if insufficient history)
            - plus_di: +DI value (or NaN)
            - minus_di: -DI value (or NaN)
            - trend_strong: 1.0 if ADX >= threshold, 0.0 otherwise (or NaN)
            - trend_weak: 1.0 if ADX < threshold, 0.0 otherwise (or NaN)
            - usable: 1.0 if sufficient history, 0.0 otherwise

        Examples:
            >>> adx = ADX(period=3, threshold=20.0)
            >>> # Need period + 1 bars for initial calculation
            >>> for h, l, c in [(100, 99, 99.5), (101, 100, 100.5), 
            ...                  (102, 101, 101.5), (103, 102, 102.5)]:
            ...     result = adx.update(h, l, c)
            >>> assert result['usable'] == 1.0
        """
        # Store history
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        # Need at least period + 1 bars
        if len(self._closes) < self.period + 1:
            return {
                "adx_value": np.nan,
                "plus_di": np.nan,
                "minus_di": np.nan,
                "trend_strong": np.nan,
                "trend_weak": np.nan,
                "usable": 0.0,
            }

        # Calculate True Range
        tr = self._calculate_tr()

        # Calculate Directional Movement
        plus_dm, minus_dm = self._calculate_dm()

        # Initialize smoothed values on first valid calculation
        if self._smoothed_tr is None:
            # Use SMA for initial smoothing
            idx_start = len(self._closes) - self.period - 1
            self._smoothed_tr = np.mean(
                [
                    self._calculate_tr_single(i)
                    for i in range(idx_start, idx_start + self.period)
                ]
            )
            self._smoothed_plus_dm = np.mean(
                [
                    self._calculate_dm_single(i)[0]
                    for i in range(idx_start, idx_start + self.period)
                ]
            )
            self._smoothed_minus_dm = np.mean(
                [
                    self._calculate_dm_single(i)[1]
                    for i in range(idx_start, idx_start + self.period)
                ]
            )
        else:
            # Wilder's smoothing: smoothed = (prev_smoothed * (period - 1) + current) / period
            self._smoothed_tr = (self._smoothed_tr * (self.period - 1) + tr) / self.period
            self._smoothed_plus_dm = (
                self._smoothed_plus_dm * (self.period - 1) + plus_dm
            ) / self.period
            self._smoothed_minus_dm = (
                self._smoothed_minus_dm * (self.period - 1) + minus_dm
            ) / self.period

        # Calculate Directional Indicators
        if self._smoothed_tr > 0:
            plus_di = 100 * (self._smoothed_plus_dm / self._smoothed_tr)
            minus_di = 100 * (self._smoothed_minus_dm / self._smoothed_tr)
        else:
            plus_di = 0.0
            minus_di = 0.0

        # Calculate DX
        di_sum = plus_di + minus_di
        if di_sum > 0:
            dx = 100 * abs(plus_di - minus_di) / di_sum
        else:
            dx = 0.0

        # Calculate ADX (smoothed DX)
        if self._smoothed_dx is None:
            # Initialize with first DX
            self._smoothed_dx = dx
        else:
            # Wilder's smoothing for ADX
            self._smoothed_dx = (self._smoothed_dx * (self.period - 1) + dx) / self.period

        adx_value = self._smoothed_dx

        # Trend flags
        trend_strong = 1.0 if adx_value >= self.threshold else 0.0
        trend_weak = 1.0 if adx_value < self.threshold else 0.0

        return {
            "adx_value": adx_value,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "trend_strong": trend_strong,
            "trend_weak": trend_weak,
            "usable": 1.0,
        }

    def _calculate_tr(self) -> float:
        """Calculate True Range for current bar."""
        return self._calculate_tr_single(len(self._closes) - 1)

    def _calculate_tr_single(self, idx: int) -> float:
        """Calculate True Range for specific index."""
        high = self._highs[idx]
        low = self._lows[idx]
        prev_close = self._closes[idx - 1] if idx > 0 else self._closes[idx]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        return tr

    def _calculate_dm(self) -> tuple[float, float]:
        """Calculate Directional Movement for current bar."""
        return self._calculate_dm_single(len(self._closes) - 1)

    def _calculate_dm_single(self, idx: int) -> tuple[float, float]:
        """Calculate Directional Movement for specific index."""
        if idx == 0:
            return 0.0, 0.0

        high = self._highs[idx]
        low = self._lows[idx]
        prev_high = self._highs[idx - 1]
        prev_low = self._lows[idx - 1]

        high_diff = high - prev_high
        low_diff = prev_low - low

        plus_dm = 0.0
        minus_dm = 0.0

        if high_diff > low_diff and high_diff > 0:
            plus_dm = high_diff
        if low_diff > high_diff and low_diff > 0:
            minus_dm = low_diff

        return plus_dm, minus_dm

    def reset(self) -> None:
        """Reset ADX state (for new session)."""
        self._highs = []
        self._lows = []
        self._closes = []
        self._smoothed_tr = None
        self._smoothed_plus_dm = None
        self._smoothed_minus_dm = None
        self._smoothed_dx = None
        logger.debug("ADX reset")


def calculate_adx_batch(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
    threshold: float = 18.0,
) -> Dict[str, np.ndarray]:
    """Calculate ADX for batch of data.

    Args:
        highs: Array of high prices.
        lows: Array of low prices.
        closes: Array of close prices.
        period: ADX period.
        threshold: Trend strength threshold.

    Returns:
        Dictionary with arrays:
        - adx_value: ADX values
        - plus_di: +DI values
        - minus_di: -DI values
        - trend_strong: Strong trend flags
        - trend_weak: Weak trend flags
        - usable: Usability flags

    Examples:
        >>> highs = np.array([100, 101, 102, 103, 104])
        >>> lows = np.array([99, 100, 101, 102, 103])
        >>> closes = np.array([99.5, 100.5, 101.5, 102.5, 103.5])
        >>> result = calculate_adx_batch(highs, lows, closes, period=3)
        >>> assert result['adx_value'].shape == (5,)
    """
    n = len(closes)
    adx_calc = ADX(period=period, threshold=threshold)

    adx_values = np.full(n, np.nan)
    plus_dis = np.full(n, np.nan)
    minus_dis = np.full(n, np.nan)
    trend_strong = np.full(n, np.nan)
    trend_weak = np.full(n, np.nan)
    usable = np.zeros(n)

    for i in range(n):
        result = adx_calc.update(highs[i], lows[i], closes[i])

        if result["usable"] == 1.0:
            adx_values[i] = result["adx_value"]
            plus_dis[i] = result["plus_di"]
            minus_dis[i] = result["minus_di"]
            trend_strong[i] = result["trend_strong"]
            trend_weak[i] = result["trend_weak"]
            usable[i] = 1.0

    return {
        "adx_value": adx_values,
        "plus_di": plus_dis,
        "minus_di": minus_dis,
        "trend_strong": trend_strong,
        "trend_weak": trend_weak,
        "usable": usable,
    }