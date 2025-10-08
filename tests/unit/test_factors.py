"""Test factor indicators."""

import pandas as pd
import pytest
from datetime import datetime

from orb_strategy.config import RelativeVolumeConfig, PriceActionConfig
from orb_strategy.features.factors import RelativeVolumeIndicator, PriceActionIndicator


def test_relative_volume():
    """Test relative volume factor."""
    config = RelativeVolumeConfig(
        enabled=True,
        lookback=5,
        spike_mult=1.5,
    )

    indicator = RelativeVolumeIndicator(config)

    # Create data with volume spike
    df = pd.DataFrame({
        "volume": [1000, 1000, 1000, 1000, 1000, 2000],  # Spike at end
    })

    signal = indicator.calculate(df, bar_idx=5)

    assert signal.long_signal  # Should trigger spike
    assert signal.short_signal  # Volume spike is directional neutral
    assert signal.value == 2.0  # 2000 / 1000


def test_price_action_engulfing():
    """Test bullish engulfing pattern."""
    config = PriceActionConfig(
        enabled=True,
        pivot_len=3,
        enable_engulfing=True,
        enable_structure=False,
    )

    indicator = PriceActionIndicator(config)

    # Create bullish engulfing pattern
    df = pd.DataFrame({
        "open": [100, 98],
        "high": [101, 103],
        "low": [99, 97],
        "close": [99, 102],  # Close above prev high
    })

    signal = indicator.calculate(df, bar_idx=1)

    assert signal.long_signal
    assert signal.metadata["engulfing_long"]


def test_price_action_structure():
    """Test higher high / higher low structure."""
    config = PriceActionConfig(
        enabled=True,
        pivot_len=3,
        enable_engulfing=False,
        enable_structure=True,
    )

    indicator = PriceActionIndicator(config)

    # Create uptrend structure
    df = pd.DataFrame({
        "high": [100, 101, 102, 105],  # Higher highs
        "low": [95, 96, 97, 100],  # Higher lows
        "open": [97, 98, 99, 101],
        "close": [99, 100, 101, 103],
    })

    signal = indicator.calculate(df, bar_idx=3)

    assert signal.long_signal
    assert signal.metadata.get("structure_long", False)
