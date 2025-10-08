"""Tests for adaptive opening range builder."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from orb_confluence.features.adaptive_or import (
    AdaptiveORBuilder,
    ATRProvider,
    AdaptiveORState
)
from orb_confluence.config.instrument_loader import get_instrument_config


def create_sample_bar(timestamp, open_, high, low, close, volume):
    """Create a sample bar as pandas Series."""
    return pd.Series({
        'timestamp': timestamp,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })


def test_atr_provider_initialization():
    """Test ATR provider initialization."""
    atr = ATRProvider(period=14)
    
    assert atr.period == 14
    assert len(atr.highs) == 0
    assert atr.get_atr() == 0.0


def test_atr_provider_calculation():
    """Test ATR calculation."""
    atr = ATRProvider(period=5)
    
    # Add some bars with known ranges
    for i in range(10):
        high = 100 + i + 1.0
        low = 100 + i
        close = 100 + i + 0.5
        atr.update(high, low, close)
    
    # ATR should be positive and reasonable (includes gaps between bars)
    result = atr.get_atr()
    assert 1.0 <= result <= 2.0  # Allow for gaps in the calculation


def test_atr_provider_rolling_window():
    """Test that ATR maintains rolling window."""
    atr = ATRProvider(period=5)
    
    # Add many bars
    for i in range(20):
        atr.update(100 + i, 99 + i, 99.5 + i)
    
    # Should only keep period + 1 bars
    assert len(atr.highs) <= 6  # period + 1


def test_adaptive_or_initialization():
    """Test adaptive OR builder initialization."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    assert builder.config == config
    assert builder.session_start == session_start
    assert builder.finalized is False
    assert builder.or_length_minutes is None


def test_adaptive_length_determination_low_vol():
    """Test adaptive length selection for low volatility."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    # Low normalized vol → min length
    length = builder.determine_adaptive_length(norm_vol=0.30)
    assert length == config.or_min_minutes  # 10 for ES


def test_adaptive_length_determination_normal_vol():
    """Test adaptive length selection for normal volatility."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    # Normal vol → base length
    length = builder.determine_adaptive_length(norm_vol=0.60)
    assert length == config.or_base_minutes  # 15 for ES


def test_adaptive_length_determination_high_vol():
    """Test adaptive length selection for high volatility."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    # High vol → max length
    length = builder.determine_adaptive_length(norm_vol=0.90)
    assert length == config.or_max_minutes  # 20 for ES


def test_or_update_accumulates_bars():
    """Test that OR accumulates bars and tracks high/low."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    atr.update(5800, 5750, 5775)  # Give ATR some data
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder.start_or(norm_vol=0.5)
    
    # Add bars
    for i in range(5):
        bar = create_sample_bar(
            timestamp=session_start + timedelta(minutes=i),
            open_=5780 + i,
            high=5785 + i,
            low=5778 + i,
            close=5783 + i,
            volume=1000
        )
        builder.update(bar)
    
    # Should have accumulated bars
    assert len(builder.bars) == 5
    assert builder.high == 5789  # Max of all highs
    assert builder.low == 5778   # Min of all lows


def test_or_stops_at_end_time():
    """Test that OR stops updating after end time."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    atr.update(5800, 5750, 5775)
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder.start_or(norm_vol=0.5)  # 15 minute OR
    
    # Add bars within OR window
    for i in range(10):
        bar = create_sample_bar(
            timestamp=session_start + timedelta(minutes=i),
            open_=5780,
            high=5785,
            low=5778,
            close=5783,
            volume=1000
        )
        builder.update(bar)
    
    # Add bar after OR window
    late_bar = create_sample_bar(
        timestamp=session_start + timedelta(minutes=20),
        open_=5790,
        high=5800,  # Would change high
        low=5770,   # Would change low
        close=5795,
        volume=1000
    )
    builder.update(late_bar)
    
    # High/low should not include late bar
    assert builder.high < 5800
    assert builder.low > 5770


def test_or_finalize_calculates_metrics():
    """Test that finalize calculates all metrics."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    
    # Give ATR some realistic data
    for _ in range(20):
        atr.update(5800, 5750, 5775)
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder.start_or(norm_vol=0.5)
    
    # Add bars
    for i in range(15):
        bar = create_sample_bar(
            timestamp=session_start + timedelta(minutes=i),
            open_=5780 + i * 0.2,
            high=5785 + i * 0.2,
            low=5778 + i * 0.2,
            close=5783 + i * 0.2,
            volume=1000
        )
        builder.update(bar)
    
    # Finalize
    state = builder.finalize()
    
    # Check state fields
    assert isinstance(state, AdaptiveORState)
    assert state.start_ts == session_start
    assert state.end_ts == session_start + timedelta(minutes=15)
    assert state.high > state.low
    assert state.width == state.high - state.low
    assert state.center == (state.high + state.low) / 2
    assert state.finalized is True


def test_or_width_normalization():
    """Test width normalization by ATR."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    
    # Set up ATR to return known value (50 points)
    for _ in range(20):
        atr.update(5850, 5800, 5825)  # 50 point range
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder.start_or(norm_vol=0.5)
    
    # Create 10 point OR width
    builder.update(create_sample_bar(session_start, 5780, 5785, 5778, 5783, 1000))
    builder.update(create_sample_bar(session_start + timedelta(minutes=1), 5783, 5790, 5775, 5788, 1000))
    
    state = builder.finalize()
    
    # Width should be around 15 points (5790 - 5775)
    # Normalized by ATR of ~50 → width_norm ≈ 0.3
    assert state.width > 0
    assert 0.2 <= state.width_norm <= 0.4


def test_or_validity_checks():
    """Test OR validity checking."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    
    for _ in range(20):
        atr.update(5850, 5800, 5825)
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    # Test narrow OR (invalid)
    builder_narrow = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=5800.0,
        prior_day_low=5750.0,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder_narrow.start_or(norm_vol=0.5)
    builder_narrow.update(create_sample_bar(session_start, 5780, 5781, 5779.5, 5780.5, 1000))
    
    state_narrow = builder_narrow.finalize()
    
    # Very narrow OR should be invalid
    assert state_narrow.is_valid is False
    assert state_narrow.invalid_reason is not None
    assert 'width' in state_narrow.invalid_reason.lower()


def test_or_context_metrics():
    """Test contextual metrics calculation."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    
    for _ in range(20):
        atr.update(5850, 5800, 5825)
    
    session_start = datetime(2025, 1, 1, 8, 30)
    prior_high = 5800.0
    prior_low = 5750.0
    
    builder = AdaptiveORBuilder(
        instrument_config=config,
        atr_provider=atr,
        prior_day_high=prior_high,
        prior_day_low=prior_low,
        overnight_high=5790.0,
        overnight_low=5770.0,
        session_start_ts=session_start
    )
    
    builder.start_or(norm_vol=0.5)
    
    # Build OR above prior mid
    for i in range(15):
        bar = create_sample_bar(
            timestamp=session_start + timedelta(minutes=i),
            open_=5800 + i,
            high=5810 + i,
            low=5798 + i,
            close=5805 + i,
            volume=1000
        )
        builder.update(bar)
    
    state = builder.finalize()
    
    # Center vs prior mid should be positive (OR above prior mid)
    prior_mid = (prior_high + prior_low) / 2  # 5775
    assert state.center_vs_prior_mid > 0  # OR center should be above 5775


def test_different_instruments_different_lengths():
    """Test that different instruments use different OR lengths."""
    es_config = get_instrument_config('ES')
    gc_config = get_instrument_config('GC')
    
    atr = ATRProvider()
    session_start = datetime(2025, 1, 1, 8, 30)
    
    es_builder = AdaptiveORBuilder(
        es_config, atr, 5800, 5750, 5790, 5770, session_start
    )
    
    gc_builder = AdaptiveORBuilder(
        gc_config, atr, 2600, 2550, 2590, 2570, session_start
    )
    
    # Same norm_vol, different lengths
    es_length = es_builder.determine_adaptive_length(0.5)
    gc_length = gc_builder.determine_adaptive_length(0.5)
    
    # GC should have longer base OR
    assert gc_length > es_length


def test_or_cannot_finalize_twice():
    """Test that OR cannot be finalized twice."""
    config = get_instrument_config('ES')
    atr = ATRProvider()
    atr.update(5800, 5750, 5775)
    
    session_start = datetime(2025, 1, 1, 8, 30)
    
    builder = AdaptiveORBuilder(
        config, atr, 5800, 5750, 5790, 5770, session_start
    )
    
    builder.start_or(norm_vol=0.5)
    builder.update(create_sample_bar(session_start, 5780, 5785, 5778, 5783, 1000))
    
    # First finalize
    state1 = builder.finalize()
    assert state1.finalized is True
    
    # Second finalize should raise error
    with pytest.raises(ValueError, match="already finalized"):
        builder.finalize()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
