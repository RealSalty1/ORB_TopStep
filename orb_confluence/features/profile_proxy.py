"""Profile proxy factor using prior day's value area as context.

Uses prior day high/low to approximate value area (VAH/VAL) and
checks current price position relative to those levels.
"""

from typing import Dict, Optional

import numpy as np
from loguru import logger


class ProfileProxy:
    """Prior day profile proxy for contextual alignment.

    Approximates value area using prior day's price range and quartiles.
    Checks if breakout is aligned with prior day's value area.

    Example:
        >>> proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)
        >>> result = proxy.analyze(
        ...     prior_day_high=105.0,
        ...     prior_day_low=100.0,
        ...     current_close=104.5,
        ...     or_high=103.0,
        ...     or_low=102.0,
        ...     or_finalized=True
        ... )
        >>> if result['profile_long_flag']:
        ...     print("Aligned for long breakout")
    """

    def __init__(
        self,
        val_pct: float = 0.25,
        vah_pct: float = 0.75,
    ) -> None:
        """Initialize profile proxy.

        Args:
            val_pct: Value Area Low percentile (0.25 = 25th percentile).
            vah_pct: Value Area High percentile (0.75 = 75th percentile).
        """
        if not 0.0 <= val_pct < vah_pct <= 1.0:
            raise ValueError(f"val_pct ({val_pct}) must be < vah_pct ({vah_pct})")

        self.val_pct = val_pct
        self.vah_pct = vah_pct

    def analyze(
        self,
        prior_day_high: float,
        prior_day_low: float,
        current_close: float,
        or_high: float,
        or_low: float,
        or_finalized: bool = True,
    ) -> Dict[str, float]:
        """Analyze profile alignment for breakout.

        Args:
            prior_day_high: Prior day's high.
            prior_day_low: Prior day's low.
            current_close: Current bar close.
            or_high: Opening Range high.
            or_low: Opening Range low.
            or_finalized: Whether OR is finalized (if False, returns zeros).

        Returns:
            Dictionary with:
            - val: Value Area Low (proxy)
            - vah: Value Area High (proxy)
            - mid: Value area midpoint
            - profile_long_flag: 1.0 if bullish alignment, 0.0 otherwise
            - profile_short_flag: 1.0 if bearish alignment, 0.0 otherwise

        Alignment Logic:
        - Bullish: Current price > VAH or (price in value area and OR above VAH)
        - Bearish: Current price < VAL or (price in value area and OR below VAL)

        Examples:
            >>> proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)
            >>> # Price above VAH → bullish
            >>> result = proxy.analyze(100, 90, 98, 96, 95, True)
            >>> assert result['profile_long_flag'] == 1.0
        """
        if not or_finalized:
            return {
                "val": np.nan,
                "vah": np.nan,
                "mid": np.nan,
                "profile_long_flag": 0.0,
                "profile_short_flag": 0.0,
            }

        # Calculate value area (proxy using percentiles)
        prior_range = prior_day_high - prior_day_low
        val = prior_day_low + (prior_range * self.val_pct)
        vah = prior_day_low + (prior_range * self.vah_pct)
        mid = (val + vah) / 2.0

        # Check alignment
        profile_long_flag = 0.0
        profile_short_flag = 0.0

        # Bullish alignment: price above VAH or OR positioned above value area
        if current_close > vah:
            profile_long_flag = 1.0
        elif val <= current_close <= vah and or_low > mid:
            # In value area but OR is above midpoint
            profile_long_flag = 1.0

        # Bearish alignment: price below VAL or OR positioned below value area
        if current_close < val:
            profile_short_flag = 1.0
        elif val <= current_close <= vah and or_high < mid:
            # In value area but OR is below midpoint
            profile_short_flag = 1.0

        return {
            "val": val,
            "vah": vah,
            "mid": mid,
            "profile_long_flag": profile_long_flag,
            "profile_short_flag": profile_short_flag,
        }


def calculate_profile_proxy(
    prior_day_high: float,
    prior_day_low: float,
    current_close: float,
    or_high: float,
    or_low: float,
    val_pct: float = 0.25,
    vah_pct: float = 0.75,
) -> Dict[str, float]:
    """Convenience function for profile proxy calculation.

    Args:
        prior_day_high: Prior day high.
        prior_day_low: Prior day low.
        current_close: Current close.
        or_high: OR high.
        or_low: OR low.
        val_pct: Value Area Low percentile.
        vah_pct: Value Area High percentile.

    Returns:
        Dictionary with profile metrics and flags.

    Examples:
        >>> result = calculate_profile_proxy(
        ...     prior_day_high=105.0,
        ...     prior_day_low=100.0,
        ...     current_close=104.0,
        ...     or_high=103.0,
        ...     or_low=102.0
        ... )
        >>> assert result['vah'] == 103.75  # 100 + (5 * 0.75)
    """
    proxy = ProfileProxy(val_pct=val_pct, vah_pct=vah_pct)
    return proxy.analyze(
        prior_day_high=prior_day_high,
        prior_day_low=prior_day_low,
        current_close=current_close,
        or_high=or_high,
        or_low=or_low,
        or_finalized=True,
    )