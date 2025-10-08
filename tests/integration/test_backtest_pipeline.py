"""Integration test for full backtest pipeline."""

import pytest
from pathlib import Path
from datetime import datetime

from orb_strategy.config import load_config
from orb_strategy.data import DataManager
from orb_strategy.backtest import BacktestEngine


@pytest.mark.integration
def test_full_backtest_pipeline(tmp_path: Path):
    """Test complete backtest from config to results."""
    # Create minimal config
    config_yaml = """
name: Integration_Test
version: "1.0"

instruments:
  SYN_TEST:
    symbol: TEST
    proxy_symbol: SYN_MEDIUM_BULL
    data_source: synthetic
    session_mode: rth
    session_start: "09:30:00"
    session_end: "16:00:00"
    timezone: America/New_York
    tick_size: 0.01
    point_value: 1.0
    enabled: true

orb:
  base_minutes: 15
  adaptive: false
  enable_validity_filter: false

buffers:
  fixed: 0.10
  use_atr: false

factors:
  rel_volume:
    enabled: false
  price_action:
    enabled: false
  profile_proxy:
    enabled: false
  vwap:
    enabled: false
  adx:
    enabled: false

scoring:
  enabled: false

trade:
  stop_mode: or_opposite
  partials: false
  primary_r: 1.5

governance:
  max_signals_per_day: 5
  lockout_after_losses: 10

backtest:
  start_date: "2024-01-01"
  end_date: "2024-01-02"
  initial_capital: 100000.0
  contracts_per_trade: 1
  conservative_fills: true
  random_seed: 42
  output_dir: {tmp_path}
  save_factor_matrix: false
  save_trades: true
  save_equity_curve: true

log_level: WARNING
log_to_file: false
"""

    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_yaml.format(tmp_path=tmp_path))

    # Load config
    config = load_config(config_file)

    # Run backtest
    data_manager = DataManager(cache_dir=tmp_path / "cache", enable_cache=False)
    engine = BacktestEngine(config=config, data_manager=data_manager)
    
    result = engine.run()

    # Assertions
    assert result is not None
    assert result.run_id is not None
    assert result.total_trades >= 0  # May or may not have trades
    assert result.start_time is not None
    assert result.end_time is not None
