"""Volume Weighted Average Price (VWAP) calculation.

VWAP is a trading benchmark that represents the average price
weighted by volume. Resets at session start or OR end.
"""

from typing import Dict, Optional

import numpy as np
from loguru import logger


class SessionVWAP:
    """Session-based VWAP calculator.

    Accumulates price * volume and volume, resetting at session boundaries.

    Example:
        >>> vwap = SessionVWAP()
        >>> for bar in bars:
        ...     result = vwap.update(bar['close'], bar['volume'])
        ...     if result['usable']:
        ...         print(f"VWAP: {result['vwap']:.2f}")
    """

    def __init__(self, min_bars: int = 5) -> None:
        """Initialize VWAP calculator.

        Args:
            min_bars: Minimum bars required before VWAP is usable.
        """
        self.min_bars = min_bars
        self._cum_pv: float = 0.0  # Cumulative price * volume
        self._cum_vol: float = 0.0  # Cumulative volume
        self._bar_count: int = 0

    def update(self, price: float, volume: float) -> Dict[str, float]:
        """Update VWAP with new bar.

        Args:
            price: Bar price (typically close or typical price).
            volume: Bar volume.

        Returns:
            Dictionary with:
            - vwap: Current VWAP value (or NaN if insufficient bars)
            - usable: 1.0 if usable, 0.0 otherwise
            - above_vwap: 1.0 if price > vwap, 0.0 otherwise (or NaN)
            - below_vwap: 1.0 if price < vwap, 0.0 otherwise (or NaN)

        Examples:
            >>> vwap = SessionVWAP(min_bars=2)
            >>> result = vwap.update(100.0, 1000)
            >>> assert result['usable'] == 0.0  # Need more bars
            
            >>> result = vwap.update(101.0, 1200)
            >>> assert result['usable'] == 1.0
            >>> assert result['vwap'] == pytest.approx(100.545, rel=0.01)
        """
        # Accumulate
        self._cum_pv += price * volume
        self._cum_vol += volume
        self._bar_count += 1

        # Check usability
        usable = self._bar_count >= self.min_bars and self._cum_vol > 0

        if not usable:
            return {
                "vwap": np.nan,
                "usable": 0.0,
                "above_vwap": np.nan,
                "below_vwap": np.nan,
            }

        # Calculate VWAP
        vwap = self._cum_pv / self._cum_vol

        # Alignment flags
        above_vwap = 1.0 if price > vwap else 0.0
        below_vwap = 1.0 if price < vwap else 0.0

        return {
            "vwap": vwap,
            "usable": 1.0,
            "above_vwap": above_vwap,
            "below_vwap": below_vwap,
        }

    def reset(self) -> None:
        """Reset VWAP (for new session or OR end)."""
        self._cum_pv = 0.0
        self._cum_vol = 0.0
        self._bar_count = 0
        logger.debug("SessionVWAP reset")

    def current_vwap(self) -> Optional[float]:
        """Get current VWAP value (or None if not usable)."""
        if self._bar_count >= self.min_bars and self._cum_vol > 0:
            return self._cum_pv / self._cum_vol
        return None


def calculate_vwap_batch(
    prices: np.ndarray,
    volumes: np.ndarray,
    min_bars: int = 5,
) -> Dict[str, np.ndarray]:
    """Calculate VWAP for batch of data (vectorized).

    Args:
        prices: Array of prices.
        volumes: Array of volumes.
        min_bars: Minimum bars before usable.

    Returns:
        Dictionary with arrays:
        - vwap: VWAP values
        - usable: Usability flags
        - above_vwap: Above VWAP flags
        - below_vwap: Below VWAP flags

    Examples:
        >>> prices = np.array([100, 101, 102, 103, 104])
        >>> volumes = np.array([1000, 1100, 1200, 1000, 1050])
        >>> result = calculate_vwap_batch(prices, volumes, min_bars=2)
        >>> assert result['vwap'].shape == (5,)
    """
    n = len(prices)

    # Cumulative sums
    cum_pv = np.cumsum(prices * volumes)
    cum_vol = np.cumsum(volumes)

    # Initialize outputs
    vwaps = np.full(n, np.nan)
    usable = np.zeros(n)
    above_vwap = np.full(n, np.nan)
    below_vwap = np.full(n, np.nan)

    # Calculate VWAP where usable
    usable_mask = (np.arange(n) >= min_bars - 1) & (cum_vol > 0)
    vwaps[usable_mask] = cum_pv[usable_mask] / cum_vol[usable_mask]
    usable[usable_mask] = 1.0

    # Alignment flags
    above_vwap[usable_mask] = (prices[usable_mask] > vwaps[usable_mask]).astype(float)
    below_vwap[usable_mask] = (prices[usable_mask] < vwaps[usable_mask]).astype(float)

    return {
        "vwap": vwaps,
        "usable": usable,
        "above_vwap": above_vwap,
        "below_vwap": below_vwap,
    }