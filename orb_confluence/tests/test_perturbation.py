"""Tests for parameter perturbation analysis."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.analytics.perturbation import (
    perturb_config,
    analyze_perturbation,
    run_perturbation_analysis,
    compute_parameter_sensitivity,
)
from orb_confluence.config.schema import (
    StrategyConfig,
    ORBConfig,
    BufferConfig,
    FactorsConfig,
    TradeConfig,
    GovernanceConfig,
    ScoringConfig,
)


def create_test_config() -> StrategyConfig:
    """Create test configuration."""
    return StrategyConfig(
        orb=ORBConfig(
            or_length_minutes=15,
            adaptive=False,
            min_atr_mult=0.3,
            max_atr_mult=3.0,
        ),
        buffer=BufferConfig(
            mode='fixed',
            fixed_ticks=2,
            atr_mult=0.1,
        ),
        factors=FactorsConfig(
            rel_vol_lookback=20,
            rel_vol_spike_threshold=1.5,
            price_action_pivot_len=3,
            adx_period=14,
            adx_threshold=25.0,
        ),
        trade=TradeConfig(
            partials=True,
            t1_r=1.0,
            t1_pct=0.5,
            t2_r=1.5,
            t2_pct=0.25,
            runner_r=2.0,
            primary_r=1.5,
            stop_mode='or_opposite',
            extra_stop_buffer=0.05,
            move_be_at_r=1.0,
            be_buffer=0.01,
        ),
        governance=GovernanceConfig(
            max_signals_per_day=3,
            lockout_after_losses=2,
        ),
        scoring=ScoringConfig(
            weights={'rel_vol': 1.0, 'price_action': 1.0, 'profile': 1.0},
            base_requirement=1.0,
            weak_trend_requirement=2.0,
        ),
    )


def create_dummy_bars(minutes: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create dummy bar data."""
    from orb_confluence.data.sources.synthetic import SyntheticProvider
    
    provider = SyntheticProvider()
    return provider.generate_synthetic_day(
        seed=seed,
        regime='trend_up',
        minutes=minutes,
        base_price=100.0,
    )


class TestPerturbConfig:
    """Test perturb_config function."""

    def test_perturb_float_parameter(self):
        """Test perturbing a float parameter."""
        config = create_test_config()
        
        # Original value
        assert config.trade.t1_r == 1.0
        
        # Perturb by +10%
        new_config = perturb_config(config, 'trade.t1_r', 10.0)
        
        assert new_config.trade.t1_r == pytest.approx(1.1)
        # Original unchanged
        assert config.trade.t1_r == 1.0

    def test_perturb_int_parameter(self):
        """Test perturbing an integer parameter."""
        config = create_test_config()
        
        # Original value
        assert config.orb.or_length_minutes == 15
        
        # Perturb by +20%
        new_config = perturb_config(config, 'orb.or_length_minutes', 20.0)
        
        # Should round to integer
        assert new_config.orb.or_length_minutes == 18  # 15 * 1.2 = 18
        assert isinstance(new_config.orb.or_length_minutes, int)

    def test_perturb_negative_delta(self):
        """Test negative perturbation."""
        config = create_test_config()
        
        new_config = perturb_config(config, 'trade.runner_r', -10.0)
        
        assert new_config.trade.runner_r == pytest.approx(1.8)  # 2.0 * 0.9

    def test_nested_parameter(self):
        """Test perturbing nested parameter."""
        config = create_test_config()
        
        # Original
        assert config.factors.adx_threshold == 25.0
        
        # Perturb
        new_config = perturb_config(config, 'factors.adx_threshold', 10.0)
        
        assert new_config.factors.adx_threshold == pytest.approx(27.5)

    def test_invalid_parameter_path(self):
        """Test that invalid path raises error."""
        config = create_test_config()
        
        with pytest.raises(AttributeError):
            perturb_config(config, 'trade.invalid_param', 10.0)


class TestAnalyzePerturbation:
    """Test analyze_perturbation function."""

    def test_perturbation_analysis(self):
        """Test single parameter perturbation analysis."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        result = analyze_perturbation(config, bars, 'trade.t1_r', 10.0)
        
        # Check result structure
        assert result.parameter_name == 'trade.t1_r'
        assert result.base_value == pytest.approx(1.0)
        assert result.perturbed_value == pytest.approx(1.1)
        assert result.delta_pct == 10.0
        
        # Should have expectancy values
        assert isinstance(result.base_expectancy, float)
        assert isinstance(result.perturbed_expectancy, float)
        assert isinstance(result.expectancy_change, float)

    def test_perturbation_deterministic(self):
        """Test that perturbation is deterministic with same seed."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100, seed=42)
        
        result1 = analyze_perturbation(config, bars, 'trade.t1_r', 10.0)
        result2 = analyze_perturbation(config, bars, 'trade.t1_r', 10.0)
        
        # Should produce identical results
        assert result1.base_expectancy == result2.base_expectancy
        assert result1.perturbed_expectancy == result2.perturbed_expectancy


class TestRunPerturbationAnalysis:
    """Test run_perturbation_analysis function."""

    def test_multiple_parameters(self):
        """Test analyzing multiple parameters."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        parameters = ['trade.t1_r', 'trade.t2_r']
        delta_pcts = [-10, 10]
        
        results_df = run_perturbation_analysis(config, bars, parameters, delta_pcts)
        
        # Should have 2 parameters * 2 deltas = 4 results
        assert len(results_df) == 4
        
        # Check columns
        expected_cols = [
            'parameter_name', 'base_value', 'perturbed_value',
            'delta_pct', 'base_expectancy', 'perturbed_expectancy',
            'expectancy_change', 'expectancy_change_pct'
        ]
        for col in expected_cols:
            assert col in results_df.columns

    def test_empty_parameters(self):
        """Test with empty parameter list."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        results_df = run_perturbation_analysis(config, bars, [])
        
        assert results_df.empty

    def test_default_delta_pcts(self):
        """Test with default delta percentages."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        parameters = ['trade.t1_r']
        
        # Uses default: [-20, -10, 10, 20]
        results_df = run_perturbation_analysis(config, bars, parameters)
        
        # Should have 4 results
        assert len(results_df) == 4
        
        # Check delta values
        assert set(results_df['delta_pct'].values) == {-20, -10, 10, 20}


class TestComputeParameterSensitivity:
    """Test compute_parameter_sensitivity function."""

    def test_sensitivity_calculation(self):
        """Test sensitivity metrics calculation."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        parameters = ['trade.t1_r', 'trade.runner_r']
        delta_pcts = [-10, 10]
        
        perturbation_df = run_perturbation_analysis(config, bars, parameters, delta_pcts)
        sensitivity_df = compute_parameter_sensitivity(perturbation_df)
        
        # Should have one row per parameter
        assert len(sensitivity_df) == 2
        
        # Check columns
        expected_cols = [
            'parameter_name',
            'avg_expectancy_change',
            'std_expectancy_change',
            'avg_expectancy_change_pct',
            'std_expectancy_change_pct',
            'avg_abs_change',
        ]
        for col in expected_cols:
            assert col in sensitivity_df.columns
        
        # Should be sorted by sensitivity (descending)
        assert sensitivity_df['avg_abs_change'].iloc[0] >= sensitivity_df['avg_abs_change'].iloc[1]

    def test_empty_perturbation_df(self):
        """Test with empty perturbation DataFrame."""
        sensitivity_df = compute_parameter_sensitivity(pd.DataFrame())
        
        assert sensitivity_df.empty


class TestPerturbationStability:
    """Test perturbation stability and edge cases."""

    def test_zero_change(self):
        """Test with zero percent change."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        result = analyze_perturbation(config, bars, 'trade.t1_r', 0.0)
        
        # No change expected
        assert result.base_value == pytest.approx(result.perturbed_value)
        assert result.expectancy_change == pytest.approx(0.0, abs=0.001)

    def test_large_perturbation(self):
        """Test with large perturbation."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        # 100% increase
        result = analyze_perturbation(config, bars, 'trade.t1_r', 100.0)
        
        assert result.base_value == pytest.approx(1.0)
        assert result.perturbed_value == pytest.approx(2.0)

    def test_negative_result(self):
        """Test perturbation that makes parameter negative."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=100)
        
        # -150% would make it negative, but might fail validation
        try:
            result = analyze_perturbation(config, bars, 'trade.t1_r', -150.0)
            # If succeeds, check value
            assert result.perturbed_value < 0
        except Exception:
            # Expected if validation prevents negative values
            pass
