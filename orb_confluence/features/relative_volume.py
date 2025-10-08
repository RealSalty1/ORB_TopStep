"""Relative Volume calculation with spike detection.

Calculates volume relative to its moving average, useful for
participation confirmation in breakout scenarios.
"""

from typing import Dict, Optional

import numpy as np
from loguru import logger


class RelativeVolume:
    """Relative volume calculator with spike detection.

    Tracks rolling volume history and calculates relative volume
    as current volume / average volume.

    Example:
        >>> rel_vol = RelativeVolume(lookback=20, spike_mult=1.5)
        >>> for volume in volumes:
        ...     result = rel_vol.update(volume)
        ...     if result['spike_flag']:
        ...         print(f"Volume spike detected: {result['rel_vol']:.2f}x")
    """

    def __init__(
        self,
        lookback: int = 20,
        spike_mult: float = 1.5,
        min_history: Optional[int] = None,
    ) -> None:
        """Initialize relative volume calculator.

        Args:
            lookback: Number of bars for volume moving average.
            spike_mult: Multiplier threshold for spike detection (e.g., 1.5 = 150% of avg).
            min_history: Minimum history required before usable (default: lookback + 5).
        """
        self.lookback = lookback
        self.spike_mult = spike_mult
        self.min_history = min_history if min_history is not None else lookback + 5

        # Rolling volume buffer
        self._volumes: list[float] = []

    def update(self, volume: float) -> Dict[str, float]:
        """Update with new volume bar.

        Args:
            volume: Current bar volume.

        Returns:
            Dictionary with:
            - rel_vol: Relative volume (current / average), or NaN if insufficient history
            - spike_flag: 1.0 if spike detected, 0.0 otherwise, or NaN
            - usable: 1.0 if sufficient history, 0.0 otherwise

        Examples:
            >>> rel_vol = RelativeVolume(lookback=5, spike_mult=2.0)
            >>> # First 5 bars: insufficient history
            >>> result = rel_vol.update(1000)
            >>> assert result['usable'] == 0.0
            >>> assert np.isnan(result['rel_vol'])
            
            >>> # After 6+ bars: usable
            >>> for v in [1000, 1100, 1200, 1000, 1050, 3000]:
            ...     result = rel_vol.update(v)
            >>> assert result['usable'] == 1.0
            >>> assert result['spike_flag'] == 1.0  # 3000 > 2.0 * avg
        """
        # Add to buffer
        self._volumes.append(volume)

        # Trim to lookback window
        if len(self._volumes) > self.lookback:
            self._volumes = self._volumes[-self.lookback :]

        # Check if we have enough history
        usable = len(self._volumes) >= self.min_history

        if not usable:
            return {
                "rel_vol": np.nan,
                "spike_flag": np.nan,
                "usable": 0.0,
            }

        # Calculate average volume (excluding current bar for fairness)
        if len(self._volumes) > 1:
            avg_volume = np.mean(self._volumes[:-1])
        else:
            avg_volume = self._volumes[0]

        # Avoid division by zero
        if avg_volume <= 0:
            return {
                "rel_vol": np.nan,
                "spike_flag": np.nan,
                "usable": 0.0,
            }

        # Calculate relative volume
        rel_vol = volume / avg_volume

        # Check for spike
        spike_flag = 1.0 if rel_vol >= self.spike_mult else 0.0

        return {
            "rel_vol": rel_vol,
            "spike_flag": spike_flag,
            "usable": 1.0,
        }

    def reset(self) -> None:
        """Reset internal state (for new session)."""
        self._volumes = []
        logger.debug("RelativeVolume reset")


def calculate_relative_volume_batch(
    volumes: np.ndarray,
    lookback: int = 20,
    spike_mult: float = 1.5,
) -> Dict[str, np.ndarray]:
    """Calculate relative volume for batch of data (vectorized).

    Args:
        volumes: Array of volume values.
        lookback: Lookback period for average.
        spike_mult: Spike multiplier threshold.

    Returns:
        Dictionary with arrays:
        - rel_vol: Relative volume values
        - spike_flag: Spike detection flags
        - usable: Usability flags

    Examples:
        >>> volumes = np.array([1000, 1100, 1000, 1050, 2000])
        >>> result = calculate_relative_volume_batch(volumes, lookback=3, spike_mult=1.5)
        >>> assert result['rel_vol'].shape == (5,)
    """
    n = len(volumes)
    rel_vols = np.full(n, np.nan)
    spike_flags = np.full(n, np.nan)
    usable = np.zeros(n)

    # Calculate rolling average
    for i in range(n):
        start_idx = max(0, i - lookback + 1)
        window = volumes[start_idx:i]

        # Need at least lookback bars
        if len(window) >= lookback:
            avg_vol = np.mean(window)
            if avg_vol > 0:
                rel_vols[i] = volumes[i] / avg_vol
                spike_flags[i] = 1.0 if rel_vols[i] >= spike_mult else 0.0
                usable[i] = 1.0

    return {
        "rel_vol": rel_vols,
        "spike_flag": spike_flags,
        "usable": usable,
    }