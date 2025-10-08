"""Tests for dual-layer OR system."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.features.or_layers import (
    DualORBuilder,
    DualORState,
    calculate_dual_or_from_bars,
)


@pytest.fixture
def sample_bars():
    """Create sample bars for testing."""
    start = datetime(2024, 1, 2, 14, 30)
    bars = []
    
    for i in range(20):
        bar = pd.Series({
            "timestamp_utc": start + timedelta(minutes=i),
            "open": 5000.0 + i * 0.5,
            "high": 5001.0 + i * 0.5,
            "low": 4999.0 + i * 0.5,
            "close": 5000.5 + i * 0.5,
            "volume": 1000,
        })
        bars.append(bar)
    
    return bars


def test_dual_or_builder_initialization():
    """Test DualORBuilder initialization."""
    start_ts = datetime(2024, 1, 2, 14, 30)
    
    builder = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=15,
        atr_14=2.5,
        atr_60=3.0,
    )
    
    assert builder.start_ts == start_ts
    assert builder.micro_minutes == 5
    assert builder.micro_end_ts == start_ts + timedelta(minutes=5)
    assert not builder.micro_finalized
    assert not builder.primary_finalized


def test_dual_or_basic_accumulation(sample_bars):
    """Test basic OR accumulation."""
    start_ts = datetime(2024, 1, 2, 14, 30)
    
    builder = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=15,
    )
    
    # Feed first 5 bars (micro OR)
    for bar in sample_bars[:5]:
        builder.update(bar)
    
    # Check micro OR not finalized yet
    assert not builder.micro_finalized
    
    # Finalize micro
    builder.finalize_if_due(sample_bars[5]["timestamp_utc"])
    
    assert builder.micro_finalized
    assert not builder.primary_finalized
    
    state = builder.state()
    assert state.micro_finalized
    assert state.micro_width > 0


def test_dual_or_adaptive_duration():
    """Test adaptive primary OR duration."""
    start_ts = datetime(2024, 1, 2, 14, 30)
    
    # Low volatility (atr_14 < 0.35 * atr_60)
    builder_low = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=15,
        primary_min_minutes=10,
        primary_max_minutes=20,
        atr_14=1.0,
        atr_60=3.0,  # normalized_vol = 0.33
        low_vol_threshold=0.35,
        high_vol_threshold=0.85,
    )
    
    # Should use minimum duration
    assert builder_low.primary_duration == 10
    
    # High volatility
    builder_high = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=15,
        primary_min_minutes=10,
        primary_max_minutes=20,
        atr_14=3.0,
        atr_60=3.0,  # normalized_vol = 1.0
        low_vol_threshold=0.35,
        high_vol_threshold=0.85,
    )
    
    # Should use maximum duration
    assert builder_high.primary_duration == 20


def test_dual_or_width_ratio(sample_bars):
    """Test width ratio calculation."""
    start_ts = datetime(2024, 1, 2, 14, 30)
    
    builder = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=10,
    )
    
    # Feed all bars
    for bar in sample_bars[:10]:
        builder.update(bar)
    
    # Finalize both
    builder.finalize_if_due(sample_bars[10]["timestamp_utc"])
    
    state = builder.state()
    
    # Width ratio should be >= 1.0 (primary >= micro)
    assert state.width_ratio >= 1.0


def test_dual_or_normalized_width():
    """Test normalized width calculation."""
    start_ts = datetime(2024, 1, 2, 14, 30)
    
    builder = DualORBuilder(
        start_ts=start_ts,
        micro_minutes=5,
        primary_base_minutes=10,
        atr_14=2.5,
    )
    
    bars = []
    for i in range(10):
        bar = pd.Series({
            "timestamp_utc": start_ts + timedelta(minutes=i),
            "high": 5005.0,
            "low": 5000.0,
            "close": 5002.5,
        })
        builder.update(bar)
        bars.append(bar)
    
    builder.finalize_if_due(bars[-1]["timestamp_utc"] + timedelta(minutes=1))
    
    state = builder.state()
    
    # Width should be 5.0, ATR 2.5, so norm = 2.0
    assert state.micro_width_norm == pytest.approx(2.0, abs=0.1)
    assert state.primary_width_norm == pytest.approx(2.0, abs=0.1)


def test_calculate_dual_or_from_bars_batch():
    """Test batch OR calculation."""
    start = datetime(2024, 1, 2, 14, 30)
    
    bars = []
    for i in range(20):
        bars.append({
            "timestamp_utc": start + timedelta(minutes=i),
            "high": 5005.0 + i * 0.1,
            "low": 5000.0 + i * 0.1,
        })
    
    df = pd.DataFrame(bars)
    
    state = calculate_dual_or_from_bars(
        df=df,
        session_start=start,
        micro_minutes=5,
        primary_minutes=15,
        atr_value=2.5,
    )
    
    assert state.micro_finalized
    assert state.primary_finalized
    assert state.micro_width > 0
    assert state.primary_width >= state.micro_width

