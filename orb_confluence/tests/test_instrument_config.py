"""Tests for instrument configuration loading."""

import pytest
from pathlib import Path
from orb_confluence.config.instrument_loader import (
    InstrumentConfigLoader,
    get_instrument_config,
    get_all_instruments
)


def test_config_loader_initialization():
    """Test that config loader initializes and loads all instruments."""
    loader = InstrumentConfigLoader()
    
    # Should have loaded all 5 instruments
    assert len(loader.configs) == 5
    
    # Check all expected symbols
    expected_symbols = ['ES', 'NQ', 'CL', 'GC', '6E']
    for symbol in expected_symbols:
        assert symbol in loader.configs


def test_es_config_structure():
    """Test ES configuration has all required fields."""
    config = get_instrument_config('ES')
    
    # Basic info
    assert config.symbol == 'ES'
    assert config.display_name == 'E-mini S&P 500'
    assert config.yahoo_symbol == 'ES=F'
    
    # Contract specs
    assert config.tick_size == 0.25
    assert config.tick_value == 12.50
    assert config.tick_value_micro == 1.25
    
    # Session times
    assert config.session_start == '08:30'
    assert config.session_end == '15:00'
    
    # OR parameters
    assert config.or_base_minutes == 15
    assert config.or_min_minutes == 10
    assert config.or_max_minutes == 20
    assert config.or_low_vol_threshold == 0.35
    assert config.or_high_vol_threshold == 0.85
    
    # Validity
    assert config.validity_min_width_norm == 0.18
    assert config.validity_max_width_norm == 0.85
    
    # Buffer
    assert config.buffer_base_points == 0.75
    assert config.buffer_volatility_scalar == 0.25
    
    # Stop
    assert config.stop_min_points == 3.0
    assert config.stop_max_risk_r == 1.4
    
    # Targets
    assert config.target_t1_r == 1.0
    assert config.target_t1_fraction == 0.40
    assert config.target_t2_r == 1.8
    assert config.target_runner_r == 3.2
    
    # Time stop
    assert config.time_stop_enabled is True
    assert config.time_stop_minutes == 25
    assert config.time_stop_min_progress_r == 0.4
    
    # Volume
    assert config.volume_cum_ratio_min == 0.85
    assert config.volume_cum_ratio_max == 1.35
    assert config.volume_spike_threshold_mult == 2.2
    assert config.volume_min_drive_energy == 0.35


def test_nq_config_differences():
    """Test NQ has different parameters than ES."""
    nq = get_instrument_config('NQ')
    es = get_instrument_config('ES')
    
    # NQ should have larger buffer (more volatile)
    assert nq.buffer_base_points > es.buffer_base_points
    
    # NQ should have higher stop floor
    assert nq.stop_min_points > es.stop_min_points
    
    # NQ should have shorter time stop
    assert nq.time_stop_minutes < es.time_stop_minutes


def test_cl_config_special_params():
    """Test CL has appropriate parameters for energy futures."""
    config = get_instrument_config('CL')
    
    # CL has earlier session start
    assert config.session_start == '08:00'
    
    # CL has smaller tick size (cents)
    assert config.tick_size == 0.01
    
    # CL allows higher volume variance
    assert config.volume_cum_ratio_max >= 1.5
    
    # CL has higher spike tolerance
    assert config.volume_spike_threshold_mult >= 2.5


def test_gc_6e_config():
    """Test GC and 6E configurations."""
    gc = get_instrument_config('GC')
    e6 = get_instrument_config('6E')
    
    # Both start earlier than equity futures
    assert gc.session_start == '07:20'
    assert e6.session_start == '07:20'
    
    # Both have longer base OR
    assert gc.or_base_minutes >= 20
    assert e6.or_base_minutes >= 20
    
    # 6E has very small tick size
    assert e6.tick_size == 0.00005


def test_get_all_instruments():
    """Test getting all instruments."""
    all_instruments = get_all_instruments()
    
    assert len(all_instruments) == 5
    assert 'ES' in all_instruments
    assert 'NQ' in all_instruments
    assert 'CL' in all_instruments
    assert 'GC' in all_instruments
    assert '6E' in all_instruments


def test_invalid_symbol():
    """Test requesting invalid symbol raises error."""
    with pytest.raises(ValueError, match="No configuration found"):
        get_instrument_config('INVALID')


def test_config_singleton():
    """Test that config loader uses singleton pattern."""
    config1 = get_instrument_config('ES')
    config2 = get_instrument_config('ES')
    
    # Should return same loader instance
    assert config1.symbol == config2.symbol


def test_typical_adr_values():
    """Test that typical ADR values are reasonable."""
    es = get_instrument_config('ES')
    nq = get_instrument_config('NQ')
    
    # NQ should have larger typical ADR than ES (higher nominal price)
    assert nq.typical_adr > es.typical_adr
    
    # ES typical ADR should be reasonable (30-60 points)
    assert 30 <= es.typical_adr <= 100


def test_correlation_instruments():
    """Test correlation instrument definitions."""
    es = get_instrument_config('ES')
    nq = get_instrument_config('NQ')
    cl = get_instrument_config('CL')
    
    # ES and NQ should reference each other
    assert 'NQ' in es.correlation_instruments
    assert 'ES' in nq.correlation_instruments
    
    # CL should be independent
    assert len(cl.correlation_instruments) == 0


def test_preferred_contract_types():
    """Test preferred contract specifications."""
    configs = get_all_instruments()
    
    for symbol, config in configs.items():
        # All should prefer micro contracts to start
        assert config.preferred_contract.startswith('M')
        
        # Should have reasonable scale-up threshold
        assert config.scale_to_mini_at_r >= 5.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
