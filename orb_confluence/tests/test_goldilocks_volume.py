"""Tests for Goldilocks volume filter."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from orb_confluence.features.goldilocks_volume import (
    TimeOfDayVolumeProfile,
    GoldilocksVolumeFilter,
    create_goldilocks_filter_from_config
)
from orb_confluence.config.instrument_loader import get_instrument_config


def create_sample_session(base_time, minutes=30, base_volume=1000, volatility=0.1):
    """Create sample session data."""
    timestamps = [base_time + timedelta(minutes=i) for i in range(minutes)]
    volumes = [base_volume * (1 + np.random.normal(0, volatility)) for _ in range(minutes)]
    opens = [100 + i * 0.1 for i in range(minutes)]
    closes = [100 + i * 0.1 + np.random.normal(0, 0.5) for i in range(minutes)]
    
    return pd.DataFrame({
        'timestamp': timestamps,
        'volume': volumes,
        'open': opens,
        'close': closes
    })


def test_tod_profile_initialization():
    """Test time-of-day profile initialization."""
    profile = TimeOfDayVolumeProfile(lookback_sessions=30)
    
    assert profile.lookback_sessions == 30
    assert profile.session_count == 0
    assert len(profile.minute_profiles) == 0


def test_tod_profile_update():
    """Test updating time-of-day profile with session data."""
    profile = TimeOfDayVolumeProfile(lookback_sessions=5)
    
    # Create and add 3 sessions
    base_time = datetime(2025, 1, 1, 8, 30)
    for session in range(3):
        session_data = create_sample_session(base_time, minutes=15)
        profile.update(session_data)
    
    assert profile.session_count == 3
    assert len(profile.minute_profiles) > 0


def test_tod_profile_expected_volume():
    """Test getting expected volume for a minute."""
    profile = TimeOfDayVolumeProfile(lookback_sessions=5)
    base_time = datetime(2025, 1, 1, 8, 30)  # 8:30 = minute 510
    
    # Add multiple sessions with consistent volume
    for _ in range(5):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000, volatility=0.05)
        profile.update(session_data)
    
    # Get expected volume for first minute (8:30)
    minute_of_day = 8 * 60 + 30  # 510
    expected = profile.get_expected_volume(minute_of_day)
    
    # Should be around 1000
    assert 900 <= expected <= 1100


def test_tod_profile_rolling_window():
    """Test that profile maintains rolling window."""
    profile = TimeOfDayVolumeProfile(lookback_sessions=3)
    base_time = datetime(2025, 1, 1, 8, 30)
    
    # Add 5 sessions
    for i in range(5):
        session_data = create_sample_session(base_time, minutes=5, base_volume=1000 * (i + 1))
        profile.update(session_data)
    
    # Should only keep last 3 sessions
    minute_of_day = 8 * 60 + 30
    stats = profile.get_volume_stats(minute_of_day)
    
    # Should not have all 5 sessions worth of data
    assert stats['median'] > 1000  # Later sessions had higher volume


def test_goldilocks_filter_initialization():
    """Test Goldilocks filter initialization."""
    filter_ = GoldilocksVolumeFilter(
        cum_ratio_min=0.85,
        cum_ratio_max=1.35,
        spike_threshold_mult=2.2,
        min_drive_energy=0.35
    )
    
    assert filter_.cum_ratio_min == 0.85
    assert filter_.cum_ratio_max == 1.35
    assert filter_.spike_threshold_mult == 2.2
    assert filter_.min_drive_energy == 0.35


def test_goldilocks_perfect_volume():
    """Test that perfect volume (ratio = 1.0) passes."""
    filter_ = GoldilocksVolumeFilter()
    
    # Build profile with consistent volume
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Test with matching volume
    or_bars = create_sample_session(base_time, minutes=15, base_volume=1000, volatility=0.05)
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    assert result['passes_goldilocks'] == True
    assert 0.9 <= result['cum_vol_ratio'] <= 1.1
    assert result['spike_detected'] == False


def test_goldilocks_volume_too_low():
    """Test that too-low volume fails."""
    filter_ = GoldilocksVolumeFilter(cum_ratio_min=0.85)
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Test with low volume
    or_bars = create_sample_session(base_time, minutes=15, base_volume=500)  # 50% of expected
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    assert result['passes_goldilocks'] == False
    assert result['cum_vol_ratio'] < 0.85
    assert 'volume_too_low' in ' '.join(result['fail_reasons'])


def test_goldilocks_volume_too_high():
    """Test that too-high volume fails."""
    filter_ = GoldilocksVolumeFilter(cum_ratio_max=1.35)
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Test with high volume
    or_bars = create_sample_session(base_time, minutes=15, base_volume=2000)  # 200% of expected
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    assert result['passes_goldilocks'] == False
    assert result['cum_vol_ratio'] > 1.35
    assert 'volume_too_high' in ' '.join(result['fail_reasons'])


def test_goldilocks_spike_detection():
    """Test that volume spikes are detected."""
    filter_ = GoldilocksVolumeFilter(spike_threshold_mult=2.2)
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000, volatility=0.05)
        filter_.update_profile(session_data)
    
    # Create OR bars with one massive spike
    or_bars = create_sample_session(base_time, minutes=15, base_volume=1000)
    or_bars.loc[5, 'volume'] = 5000  # Huge spike in middle
    
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    assert result['spike_detected'] is True
    assert result['max_spike_ratio'] > 2.2
    assert result['passes_goldilocks'] is False


def test_goldilocks_drive_energy():
    """Test opening drive energy calculation."""
    filter_ = GoldilocksVolumeFilter(min_drive_energy=0.35)
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Create lethargic OR (low drive energy)
    or_bars = pd.DataFrame({
        'timestamp': [base_time + timedelta(minutes=i) for i in range(15)],
        'volume': [1000] * 15,
        'open': [100.0] * 15,  # No price movement
        'close': [100.05] * 15  # Tiny closes
    })
    
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    # Should have low drive energy
    assert result['opening_drive_energy'] < 0.35
    assert 'drive_energy_low' in ' '.join(result['fail_reasons'])


def test_goldilocks_quality_score():
    """Test volume quality score calculation."""
    filter_ = GoldilocksVolumeFilter()
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Perfect OR
    or_bars = create_sample_session(base_time, minutes=15, base_volume=1000, volatility=0.05)
    result = filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    # Quality score should be high
    assert result['volume_quality_score'] > 0.6
    assert 0.0 <= result['volume_quality_score'] <= 1.0


def test_goldilocks_z_score():
    """Test z-score calculation with history."""
    filter_ = GoldilocksVolumeFilter()
    
    # Build profile
    base_time = datetime(2025, 1, 1, 8, 30)
    for _ in range(10):
        session_data = create_sample_session(base_time, minutes=15, base_volume=1000)
        filter_.update_profile(session_data)
    
    # Analyze multiple ORs to build z-score history
    for _ in range(10):
        or_bars = create_sample_session(base_time, minutes=15, base_volume=1000, volatility=0.1)
        filter_.analyze_or_volume(or_bars, or_width=5.0)
    
    # Now test an extreme volume OR
    or_bars_extreme = create_sample_session(base_time, minutes=15, base_volume=2000)
    result = filter_.analyze_or_volume(or_bars_extreme, or_width=5.0)
    
    # Should have high z-score
    assert abs(result['vol_z_score']) > 1.0


def test_goldilocks_empty_data():
    """Test handling of empty data."""
    filter_ = GoldilocksVolumeFilter()
    
    empty_df = pd.DataFrame(columns=['timestamp', 'volume', 'open', 'close'])
    result = filter_.analyze_or_volume(empty_df, or_width=5.0)
    
    assert result['passes_goldilocks'] is False
    assert 'insufficient_data' in result['fail_reasons']


def test_create_from_config():
    """Test creating filter from instrument config."""
    es_config = get_instrument_config('ES')
    filter_ = create_goldilocks_filter_from_config(es_config)
    
    assert filter_.cum_ratio_min == es_config.volume_cum_ratio_min
    assert filter_.cum_ratio_max == es_config.volume_cum_ratio_max
    assert filter_.spike_threshold_mult == es_config.volume_spike_threshold_mult
    assert filter_.min_drive_energy == es_config.volume_min_drive_energy


def test_different_instrument_thresholds():
    """Test that different instruments have different thresholds."""
    es_filter = create_goldilocks_filter_from_config(get_instrument_config('ES'))
    cl_filter = create_goldilocks_filter_from_config(get_instrument_config('CL'))
    
    # CL should have more lenient thresholds (news-driven)
    assert cl_filter.cum_ratio_max >= es_filter.cum_ratio_max
    assert cl_filter.spike_threshold_mult >= es_filter.spike_threshold_mult


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
