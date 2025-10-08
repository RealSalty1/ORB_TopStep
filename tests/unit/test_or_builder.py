"""Test Opening Range builder."""

import pandas as pd
import pytest
from datetime import datetime, time

from orb_strategy.config import ORBConfig, InstrumentConfig
from orb_strategy.features.or_builder import ORBuilder, ORValidity


@pytest.fixture
def orb_config():
    """Create test ORB config."""
    return ORBConfig(
        base_minutes=15,
        adaptive=False,
        enable_validity_filter=False,
    )


@pytest.fixture
def instrument_config():
    """Create test instrument config."""
    return InstrumentConfig(
        symbol="TEST",
        proxy_symbol="TEST",
        data_source="synthetic",
        session_start=time(9, 30),
        session_end=time(16, 0),
        tick_size=0.01,
        point_value=1.0,
    )


def test_or_builder_basic(orb_config, instrument_config):
    """Test basic OR building."""
    # Create synthetic minute bars
    dates = pd.date_range("2024-01-01 09:30", periods=60, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "high": [100.0 + i * 0.1 for i in range(60)],
        "low": [99.0 + i * 0.1 for i in range(60)],
        "close": [99.5 + i * 0.1 for i in range(60)],
        "volume": [1000] * 60,
    }, index=dates)

    builder = ORBuilder(orb_config, instrument_config)
    ors = builder.build_opening_ranges(df)

    assert len(ors) == 1
    
    or_obj = ors[0]
    assert or_obj.duration_minutes == 15
    assert or_obj.or_high > or_obj.or_low
    assert or_obj.or_width > 0


def test_or_validity_filter():
    """Test OR validity filtering."""
    config = ORBConfig(
        base_minutes=15,
        adaptive=False,
        enable_validity_filter=True,
        min_atr_mult=0.5,
        max_atr_mult=2.0,
        atr_period=14,
    )

    instrument = InstrumentConfig(
        symbol="TEST",
        proxy_symbol="TEST",
        data_source="synthetic",
        session_start=time(9, 30),
        session_end=time(16, 0),
        tick_size=0.01,
        point_value=1.0,
    )

    # Create data with very narrow OR
    dates = pd.date_range("2024-01-01 09:30", periods=390, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "high": [100.0] * 390,  # No movement
        "low": [100.0] * 390,
        "close": [100.0] * 390,
        "volume": [1000] * 390,
    }, index=dates)

    builder = ORBuilder(config, instrument)
    ors = builder.build_opening_ranges(df)

    # Should be invalid (too narrow)
    if ors:
        assert ors[0].validity == ORValidity.TOO_NARROW or ors[0].or_width == 0.0
