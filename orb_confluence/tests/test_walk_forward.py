"""Tests for walk-forward optimization."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.analytics.walk_forward import (
    create_walk_forward_windows,
    simple_grid_optimization,
    run_walk_forward,
    WalkForwardWindow,
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


def create_dummy_bars(minutes: int = 500, seed: int = 42) -> pd.DataFrame:
    """Create dummy bar data."""
    from orb_confluence.data.sources.synthetic import SyntheticProvider
    
    provider = SyntheticProvider()
    return provider.generate_synthetic_day(
        seed=seed,
        regime='trend_up',
        minutes=minutes,
        base_price=100.0,
    )


class TestCreateWalkForwardWindows:
    """Test create_walk_forward_windows function."""

    def test_basic_windowing(self):
        """Test basic window creation."""
        bars = create_dummy_bars(minutes=500)
        
        windows = create_walk_forward_windows(
            bars,
            train_bars=200,
            test_bars=100,
        )
        
        # Should create at least 1 window
        assert len(windows) > 0
        
        # Check first window
        w = windows[0]
        assert w.window_id == 0
        assert w.train_bars == 200
        assert w.test_bars == 100
        assert w.train_start < w.train_end
        assert w.test_start > w.train_end
        assert w.test_start < w.test_end

    def test_multiple_windows(self):
        """Test creation of multiple windows."""
        bars = create_dummy_bars(minutes=1000)
        
        windows = create_walk_forward_windows(
            bars,
            train_bars=200,
            test_bars=100,
            step_bars=100,  # Roll forward by 100 bars
        )
        
        # With 1000 bars, 200 train, 100 test, step 100:
        # Should create multiple windows
        assert len(windows) >= 2
        
        # Check window IDs are sequential
        for i, w in enumerate(windows):
            assert w.window_id == i

    def test_custom_step_size(self):
        """Test with custom step size."""
        bars = create_dummy_bars(minutes=600)
        
        # Step by 50 bars (smaller than test size)
        windows = create_walk_forward_windows(
            bars,
            train_bars=200,
            test_bars=100,
            step_bars=50,
        )
        
        # Should create more windows with smaller step
        assert len(windows) >= 2

    def test_no_windows_insufficient_data(self):
        """Test with insufficient data."""
        bars = create_dummy_bars(minutes=100)
        
        windows = create_walk_forward_windows(
            bars,
            train_bars=200,
            test_bars=100,
        )
        
        # Not enough data for even one window
        assert len(windows) == 0


class TestSimpleGridOptimization:
    """Test simple_grid_optimization function."""

    def test_basic_optimization(self):
        """Test basic grid optimization."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=200)
        
        parameter_grid = {
            'trade.t1_r': [0.8, 1.0, 1.2],
        }
        
        best_config, best_expectancy = simple_grid_optimization(
            config,
            bars,
            parameter_grid,
        )
        
        # Should return a config and expectancy
        assert isinstance(best_config, StrategyConfig)
        assert isinstance(best_expectancy, float)
        
        # Best value should be one from grid
        assert best_config.trade.t1_r in [0.8, 1.0, 1.2]

    def test_multi_parameter_optimization(self):
        """Test optimization with multiple parameters."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=200)
        
        parameter_grid = {
            'trade.t1_r': [0.9, 1.0],
            'trade.t2_r': [1.4, 1.5],
        }
        
        best_config, best_expectancy = simple_grid_optimization(
            config,
            bars,
            parameter_grid,
        )
        
        # Should test 2*2 = 4 combinations
        assert isinstance(best_config, StrategyConfig)
        
        # Best values should be from grid
        assert best_config.trade.t1_r in [0.9, 1.0]
        assert best_config.trade.t2_r in [1.4, 1.5]

    def test_single_parameter_value(self):
        """Test with single parameter value (no optimization needed)."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=200)
        
        parameter_grid = {
            'trade.t1_r': [1.0],
        }
        
        best_config, best_expectancy = simple_grid_optimization(
            config,
            bars,
            parameter_grid,
        )
        
        # Should still work with single value
        assert best_config.trade.t1_r == 1.0


class TestRunWalkForward:
    """Test run_walk_forward function."""

    def test_basic_walk_forward(self):
        """Test basic walk-forward analysis."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=500)
        
        parameter_grid = {
            'trade.t1_r': [0.9, 1.0, 1.1],
        }
        
        result = run_walk_forward(
            config,
            bars,
            train_bars=200,
            test_bars=100,
            parameter_grid=parameter_grid,
        )
        
        # Check result structure
        assert len(result.windows) > 0
        assert len(result.optimization_results) == len(result.windows)
        assert len(result.test_results) == len(result.windows)
        
        # Check aggregated metrics
        assert 'total_windows' in result.aggregated_metrics
        assert 'avg_test_expectancy' in result.aggregated_metrics
        assert 'total_test_r' in result.aggregated_metrics
        
        # Check stability metrics
        assert 'expectancy_stability' in result.stability_metrics
        assert 'positive_windows' in result.stability_metrics
        assert 'consistency_ratio' in result.stability_metrics

    def test_stability_metrics(self):
        """Test stability metrics calculation."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=700, seed=42)
        
        parameter_grid = {
            'trade.t1_r': [0.9, 1.0],
        }
        
        result = run_walk_forward(
            config,
            bars,
            train_bars=200,
            test_bars=150,
            parameter_grid=parameter_grid,
        )
        
        # Consistency ratio should be between 0 and 1
        assert 0.0 <= result.stability_metrics['consistency_ratio'] <= 1.0
        
        # Positive + negative windows should equal total
        assert (result.stability_metrics['positive_windows'] +
                result.stability_metrics['negative_windows'] ==
                result.aggregated_metrics['total_windows'])

    def test_deterministic_results(self):
        """Test that walk-forward is deterministic with same seed."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=500, seed=999)
        
        parameter_grid = {
            'trade.t1_r': [1.0, 1.1],
        }
        
        result1 = run_walk_forward(
            config,
            bars,
            train_bars=200,
            test_bars=100,
            parameter_grid=parameter_grid,
        )
        
        result2 = run_walk_forward(
            config,
            bars,
            train_bars=200,
            test_bars=100,
            parameter_grid=parameter_grid,
        )
        
        # Should produce identical results
        assert result1.aggregated_metrics['avg_test_expectancy'] == result2.aggregated_metrics['avg_test_expectancy']
        assert len(result1.windows) == len(result2.windows)

    @pytest.mark.slow
    def test_large_parameter_grid(self):
        """Test with larger parameter grid."""
        config = create_test_config()
        bars = create_dummy_bars(minutes=600)
        
        parameter_grid = {
            'trade.t1_r': [0.8, 0.9, 1.0, 1.1, 1.2],
            'trade.t2_r': [1.3, 1.4, 1.5, 1.6],
        }
        
        result = run_walk_forward(
            config,
            bars,
            train_bars=200,
            test_bars=100,
            parameter_grid=parameter_grid,
            step_bars=100,
        )
        
        # Should complete without errors
        assert len(result.windows) > 0


class TestWalkForwardWindow:
    """Test WalkForwardWindow dataclass."""

    def test_window_structure(self):
        """Test window dataclass structure."""
        window = WalkForwardWindow(
            window_id=0,
            train_start=datetime(2024, 1, 2, 9, 30),
            train_end=datetime(2024, 1, 2, 12, 30),
            test_start=datetime(2024, 1, 2, 12, 31),
            test_end=datetime(2024, 1, 2, 14, 30),
            train_bars=180,
            test_bars=120,
        )
        
        assert window.window_id == 0
        assert window.train_bars == 180
        assert window.test_bars == 120
        assert window.test_start > window.train_end
