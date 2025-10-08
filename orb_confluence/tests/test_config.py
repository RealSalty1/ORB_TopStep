"""Test configuration loading and validation."""

import pytest
from datetime import time
from pathlib import Path
from pydantic import ValidationError

from orb_confluence.config import (
    StrategyConfig,
    InstrumentConfig,
    ORBConfig,
    BuffersConfig,
    TradeConfig,
    ScoringConfig,
    BacktestConfig,
    load_config,
    get_default_config,
    resolved_config_hash,
    deep_merge,
)


class TestORBConfig:
    """Test ORB configuration validation."""

    def test_valid_orb_config(self):
        """Test valid ORB configuration."""
        config = ORBConfig(
            base_minutes=15,
            min_atr_mult=0.25,
            max_atr_mult=1.75,
            low_norm_vol=0.35,
            high_norm_vol=0.85,
        )
        assert config.base_minutes == 15
        assert config.min_atr_mult < config.max_atr_mult

    def test_invalid_atr_mult_order(self):
        """Test that min_atr_mult < max_atr_mult is enforced."""
        with pytest.raises(ValidationError, match="min_atr_mult.*must be <"):
            ORBConfig(
                base_minutes=15,
                min_atr_mult=2.0,
                max_atr_mult=1.0,
            )

    def test_invalid_norm_vol_order(self):
        """Test that low_norm_vol < high_norm_vol is enforced when adaptive."""
        with pytest.raises(ValidationError, match="low_norm_vol.*must be <"):
            ORBConfig(
                base_minutes=15,
                adaptive=True,
                low_norm_vol=0.9,
                high_norm_vol=0.3,
            )

    def test_invalid_or_minutes_order(self):
        """Test that short_or_minutes < long_or_minutes is enforced."""
        with pytest.raises(ValidationError, match="short_or_minutes.*must be <"):
            ORBConfig(
                base_minutes=15,
                adaptive=True,
                short_or_minutes=30,
                long_or_minutes=10,
            )


class TestBuffersConfig:
    """Test buffer configuration validation."""

    def test_valid_fixed_buffer(self):
        """Test valid fixed buffer."""
        config = BuffersConfig(fixed=0.10, use_atr=False)
        assert config.fixed == 0.10

    def test_valid_atr_buffer(self):
        """Test valid ATR buffer."""
        config = BuffersConfig(fixed=0.0, use_atr=True, atr_mult=0.05)
        assert config.use_atr is True

    def test_invalid_no_buffer(self):
        """Test that at least one buffer type must be set."""
        with pytest.raises(ValidationError, match="Must have either"):
            BuffersConfig(fixed=0.0, use_atr=False)


class TestTradeConfig:
    """Test trade configuration validation."""

    def test_valid_trade_with_partials(self):
        """Test valid trade config with partials."""
        config = TradeConfig(
            partials=True,
            t1_r=1.0,
            t1_pct=0.5,
            t2_r=1.5,
            t2_pct=0.25,
            runner_r=2.0,
        )
        assert config.partials is True
        assert config.runner_r > 1.5

    def test_invalid_runner_r_with_partials(self):
        """Test that runner_r > 1.5 when partials=True."""
        with pytest.raises(ValidationError, match="runner_r.*must be > 1.5"):
            TradeConfig(
                partials=True,
                t1_r=1.0,
                t1_pct=0.5,
                t2_r=1.25,
                t2_pct=0.25,
                runner_r=1.4,  # Invalid: <= 1.5
            )

    def test_invalid_target_pct_sum(self):
        """Test that t1_pct + t2_pct <= 1.0."""
        with pytest.raises(ValidationError, match="must be <= 1.0"):
            TradeConfig(
                partials=True,
                t1_r=1.0,
                t1_pct=0.6,
                t2_r=1.5,
                t2_pct=0.5,  # Sum = 1.1
                runner_r=2.0,
            )

    def test_invalid_target_r_order(self):
        """Test that t1_r < t2_r < runner_r."""
        with pytest.raises(ValidationError, match="t1_r.*must be <"):
            TradeConfig(
                partials=True,
                t1_r=1.5,
                t1_pct=0.5,
                t2_r=1.0,  # Invalid: < t1_r
                t2_pct=0.25,
                runner_r=2.0,
            )


class TestScoringConfig:
    """Test scoring configuration validation."""

    def test_valid_scoring_config(self):
        """Test valid scoring configuration."""
        config = ScoringConfig(
            enabled=True,
            base_required=2,
            weak_trend_required=3,
        )
        assert config.base_required <= config.weak_trend_required

    def test_invalid_weights(self):
        """Test that negative weights are rejected."""
        with pytest.raises(ValidationError, match="must be non-negative"):
            ScoringConfig(
                weights={"price_action": -1.0}
            )


class TestBacktestConfig:
    """Test backtest configuration validation."""

    def test_valid_date_range(self):
        """Test valid date range."""
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-03-31",
        )
        assert config.start_date < config.end_date

    def test_invalid_date_format(self):
        """Test invalid date format."""
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            BacktestConfig(
                start_date="01/01/2024",  # Wrong format
                end_date="2024-03-31",
            )

    def test_invalid_date_order(self):
        """Test that start_date < end_date."""
        with pytest.raises(ValidationError, match="must be before"):
            BacktestConfig(
                start_date="2024-03-31",
                end_date="2024-01-01",
            )


class TestStrategyConfig:
    """Test full strategy configuration."""

    def test_load_defaults(self):
        """Test loading default configuration."""
        default_path = get_default_config()
        config = load_config(default_path, use_defaults=False)

        assert config.name == "ORB_Confluence_Free"
        assert "SPY" in config.instruments
        assert config.instruments["SPY"].enabled is True

    def test_config_validation_no_enabled_instruments(self):
        """Test that at least one instrument must be enabled."""
        with pytest.raises(ValidationError, match="At least one instrument must be enabled"):
            StrategyConfig(
                name="Test",
                instruments={
                    "TEST": InstrumentConfig(
                        symbol="TEST",
                        proxy_symbol="TEST",
                        data_source="synthetic",
                        session_start=time(9, 30),
                        session_end=time(16, 0),
                        tick_size=0.01,
                        point_value=1.0,
                        enabled=False,  # Disabled
                    )
                },
                backtest=BacktestConfig(
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                ),
            )

    def test_config_validation_scoring_vs_factors(self):
        """Test that scoring requirements don't exceed enabled factors."""
        with pytest.raises(ValidationError, match="exceeds number of enabled factors"):
            StrategyConfig(
                name="Test",
                instruments={
                    "TEST": InstrumentConfig(
                        symbol="TEST",
                        proxy_symbol="TEST",
                        data_source="synthetic",
                        session_start=time(9, 30),
                        session_end=time(16, 0),
                        tick_size=0.01,
                        point_value=1.0,
                        enabled=True,
                    )
                },
                backtest=BacktestConfig(
                    start_date="2024-01-01",
                    end_date="2024-01-31",
                ),
                scoring=ScoringConfig(
                    enabled=True,
                    base_required=10,  # More than possible factors
                ),
            )


class TestConfigLoader:
    """Test configuration loader functionality."""

    def test_deep_merge(self):
        """Test deep dictionary merging."""
        base = {
            "a": 1,
            "b": {"c": 2, "d": 3},
            "e": 4,
        }
        override = {
            "b": {"c": 99},
            "f": 5,
        }

        result = deep_merge(base, override)

        assert result["a"] == 1
        assert result["b"]["c"] == 99  # Overridden
        assert result["b"]["d"] == 3  # Preserved
        assert result["e"] == 4
        assert result["f"] == 5

    def test_config_hash_deterministic(self):
        """Test that config hash is deterministic."""
        default_path = get_default_config()
        config1 = load_config(default_path, use_defaults=False)
        config2 = load_config(default_path, use_defaults=False)

        hash1 = resolved_config_hash(config1)
        hash2 = resolved_config_hash(config2)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_config_hash_changes(self):
        """Test that config hash changes when config changes."""
        default_path = get_default_config()
        config1 = load_config(default_path, use_defaults=False)

        # Modify config
        config1.orb.base_minutes = 20

        config2 = load_config(default_path, use_defaults=False)

        hash1 = resolved_config_hash(config1)
        hash2 = resolved_config_hash(config2)

        assert hash1 != hash2

    def test_yaml_merge_override(self, tmp_path):
        """Test YAML merging with user override."""
        # Create user config that overrides some defaults
        user_config = tmp_path / "user.yaml"
        user_config.write_text("""
name: Custom_Strategy
orb:
  base_minutes: 20
  adaptive: false
""")

        config = load_config(user_config, use_defaults=True)

        # Check overrides applied
        assert config.name == "Custom_Strategy"
        assert config.orb.base_minutes == 20
        assert config.orb.adaptive is False

        # Check defaults preserved
        assert "SPY" in config.instruments
        assert config.trade.partials is True


class TestInstrumentConfig:
    """Test instrument configuration validation."""

    def test_valid_instrument(self):
        """Test valid instrument configuration."""
        config = InstrumentConfig(
            symbol="ES",
            proxy_symbol="SPY",
            data_source="yahoo",
            session_start=time(8, 30),
            session_end=time(15, 0),
            tick_size=0.01,
            point_value=1.0,
        )
        assert config.symbol == "ES"
        assert config.data_source == "yahoo"

    def test_invalid_data_source(self):
        """Test invalid data source."""
        with pytest.raises(ValidationError, match="Data source must be"):
            InstrumentConfig(
                symbol="ES",
                proxy_symbol="SPY",
                data_source="invalid",
                session_start=time(8, 30),
                session_end=time(15, 0),
                tick_size=0.01,
                point_value=1.0,
            )

    def test_symbol_uppercase_conversion(self):
        """Test that symbols are converted to uppercase."""
        config = InstrumentConfig(
            symbol="es",
            proxy_symbol="spy",
            data_source="yahoo",
            session_start=time(8, 30),
            session_end=time(15, 0),
            tick_size=0.01,
            point_value=1.0,
        )
        assert config.symbol == "ES"
        assert config.proxy_symbol == "SPY"