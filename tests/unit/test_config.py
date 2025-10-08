"""Test configuration loading and validation."""

import pytest
from pathlib import Path
from orb_strategy.config import StrategyConfig, load_config, ORBConfig


def test_orb_config_validation():
    """Test ORB config validation."""
    # Valid config
    config = ORBConfig(
        base_minutes=15,
        min_atr_mult=0.25,
        max_atr_mult=1.75,
        low_norm_vol=0.35,
        high_norm_vol=0.85,
    )
    assert config.base_minutes == 15

    # Invalid: min >= max
    with pytest.raises(ValueError, match="min_atr_mult must be < max_atr_mult"):
        ORBConfig(
            base_minutes=15,
            min_atr_mult=2.0,
            max_atr_mult=1.0,
        )


def test_config_loading(tmp_path: Path):
    """Test loading config from YAML."""
    config_yaml = """
name: Test_Strategy
version: "1.0"

instruments:
  SPY:
    symbol: ES
    proxy_symbol: SPY
    data_source: yahoo
    session_mode: rth
    session_start: "08:30:00"
    session_end: "15:00:00"
    timezone: America/Chicago
    tick_size: 0.01
    point_value: 1.0
    enabled: true

backtest:
  start_date: "2024-01-01"
  end_date: "2024-01-31"
  initial_capital: 100000.0
  contracts_per_trade: 1
"""

    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_yaml)

    config = load_config(config_file)

    assert config.name == "Test_Strategy"
    assert "SPY" in config.instruments
    assert config.instruments["SPY"].proxy_symbol == "SPY"
