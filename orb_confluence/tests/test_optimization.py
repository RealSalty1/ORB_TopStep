"""Tests for hyperparameter optimization."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from orb_confluence.analytics.optimization import (
    create_objective,
    run_optimization,
    apply_optimized_params,
    analyze_optimization_results,
    compute_parameter_importance,
    OptimizationResult,
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
from orb_confluence.analytics.metrics import PerformanceMetrics


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


def create_mock_metrics(
    expectancy: float = 0.5,
    total_trades: int = 10,
    win_rate: float = 0.6,
    max_drawdown_r: float = -2.0,
    sharpe_ratio: float = 1.5,
) -> PerformanceMetrics:
    """Create mock performance metrics."""
    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=int(total_trades * win_rate),
        losing_trades=int(total_trades * (1 - win_rate)),
        win_rate=win_rate,
        total_r=expectancy * total_trades,
        average_r=expectancy,
        median_r=expectancy,
        expectancy=expectancy,
        profit_factor=2.0,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=2.0,
        max_drawdown_r=max_drawdown_r,
        max_drawdown_pct=-15.0,
        avg_winner_r=1.0,
        avg_loser_r=-0.5,
        largest_winner_r=2.0,
        largest_loser_r=-1.0,
        consecutive_wins=3,
        consecutive_losses=2,
    )


class TestCreateObjective:
    """Test create_objective function."""

    def test_objective_creation(self):
        """Test objective function creation."""
        config = create_test_config()
        bars = pd.DataFrame()  # Empty for test
        
        objective = create_objective(config, bars)
        
        assert callable(objective)

    @patch('orb_confluence.analytics.optimization.EventLoopBacktest')
    @patch('orb_confluence.analytics.optimization.compute_metrics')
    def test_objective_execution(self, mock_compute_metrics, mock_backtest_class):
        """Test objective function execution with mocked backtest."""
        config = create_test_config()
        bars = pd.DataFrame()
        
        # Mock backtest
        mock_engine = Mock()
        mock_result = Mock()
        mock_result.trades = []
        mock_engine.run.return_value = mock_result
        mock_backtest_class.return_value = mock_engine
        
        # Mock metrics
        mock_metrics = create_mock_metrics(expectancy=0.5, max_drawdown_r=-2.0)
        mock_compute_metrics.return_value = mock_metrics
        
        # Create objective
        objective = create_objective(config, bars)
        
        # Mock trial
        mock_trial = Mock()
        mock_trial.number = 0
        mock_trial.suggest_int.return_value = 2
        mock_trial.suggest_float.side_effect = [
            0.3,  # min_atr_mult
            3.0,  # max_atr_mult
            1.5,  # rel_vol_spike
            1.0,  # score_base_req
            2.0,  # score_weak_req
            1.0,  # t1_r
            1.5,  # t2_r
            2.0,  # runner_r
        ]
        
        # Run objective
        score = objective(mock_trial)
        
        # Check score calculation
        # composite = expectancy * 1.0 + max_drawdown_r * 0.3
        # = 0.5 + (-2.0 * 0.3) = 0.5 - 0.6 = -0.1
        assert score == pytest.approx(-0.1, abs=0.01)
        
        # Check that backtest was called
        mock_backtest_class.assert_called_once()

    @patch('orb_confluence.analytics.optimization.EventLoopBacktest')
    @patch('orb_confluence.analytics.optimization.compute_metrics')
    def test_objective_min_trades_penalty(self, mock_compute_metrics, mock_backtest_class):
        """Test penalty for insufficient trades."""
        config = create_test_config()
        bars = pd.DataFrame()
        
        # Mock backtest
        mock_engine = Mock()
        mock_result = Mock()
        mock_result.trades = []
        mock_engine.run.return_value = mock_result
        mock_backtest_class.return_value = mock_engine
        
        # Mock metrics with too few trades
        mock_metrics = create_mock_metrics(total_trades=2)  # min_trades=5
        mock_compute_metrics.return_value = mock_metrics
        
        # Create objective
        objective = create_objective(config, bars, min_trades=5)
        
        # Mock trial
        mock_trial = Mock()
        mock_trial.number = 0
        mock_trial.suggest_int.return_value = 2
        mock_trial.suggest_float.side_effect = [0.3, 3.0, 1.5, 1.0, 2.0, 1.0, 1.5, 2.0]
        
        # Run objective
        score = objective(mock_trial)
        
        # Should have penalty: (5 - 2) * 0.5 = 1.5
        assert score == pytest.approx(-1.5)


class TestRunOptimization:
    """Test run_optimization function."""

    @patch('orb_confluence.analytics.optimization.EventLoopBacktest')
    @patch('orb_confluence.analytics.optimization.compute_metrics')
    def test_basic_optimization(self, mock_compute_metrics, mock_backtest_class):
        """Test basic optimization run."""
        config = create_test_config()
        bars = pd.DataFrame()
        
        # Mock backtest
        mock_engine = Mock()
        mock_result = Mock()
        mock_result.trades = []
        mock_engine.run.return_value = mock_result
        mock_backtest_class.return_value = mock_engine
        
        # Mock metrics (return varying results)
        def metrics_side_effect(*args, **kwargs):
            import random
            return create_mock_metrics(
                expectancy=random.uniform(0.3, 0.7),
                max_drawdown_r=random.uniform(-3.0, -1.0),
            )
        
        mock_compute_metrics.side_effect = metrics_side_effect
        
        # Run optimization with few trials
        result = run_optimization(
            config,
            bars,
            n_trials=5,
            study_name='test_study',
        )
        
        # Check result
        assert isinstance(result, OptimizationResult)
        assert result.study_name == 'test_study'
        assert result.n_trials == 5
        assert len(result.best_params) > 0
        assert not result.trials_df.empty

    @pytest.mark.slow
    @patch('orb_confluence.analytics.optimization.EventLoopBacktest')
    @patch('orb_confluence.analytics.optimization.compute_metrics')
    def test_optimization_convergence(self, mock_compute_metrics, mock_backtest_class):
        """Test that optimization finds better solutions over time."""
        config = create_test_config()
        bars = pd.DataFrame()
        
        # Mock backtest
        mock_engine = Mock()
        mock_result = Mock()
        mock_result.trades = []
        mock_engine.run.return_value = mock_result
        mock_backtest_class.return_value = mock_engine
        
        # Mock metrics with improving trend
        trial_count = [0]
        
        def metrics_side_effect(*args, **kwargs):
            # Improve over time
            trial_count[0] += 1
            base_exp = 0.3 + (trial_count[0] / 20.0)  # Gradually improve
            return create_mock_metrics(expectancy=base_exp)
        
        mock_compute_metrics.side_effect = metrics_side_effect
        
        # Run optimization
        result = run_optimization(config, bars, n_trials=20)
        
        # Check that later trials are better on average
        trials_df = result.trials_df.sort_values('trial_number')
        first_half = trials_df.head(10)['value'].mean()
        second_half = trials_df.tail(10)['value'].mean()
        
        # Second half should be better (allowing some variance)
        assert second_half >= first_half * 0.9  # Within 10%


class TestApplyOptimizedParams:
    """Test apply_optimized_params function."""

    def test_apply_parameters(self):
        """Test applying optimized parameters to config."""
        config = create_test_config()
        
        optimized_params = {
            'buffer_fixed_ticks': 3,
            'min_atr_mult': 0.25,
            'max_atr_mult': 3.5,
            'rel_vol_spike_threshold': 1.7,
            'scoring_base_requirement': 1.5,
            'trade_t1_r': 1.1,
            'trade_runner_r': 2.2,
        }
        
        new_config = apply_optimized_params(config, optimized_params)
        
        # Check parameters were applied
        assert new_config.buffer.fixed_ticks == 3
        assert new_config.orb.min_atr_mult == pytest.approx(0.25)
        assert new_config.orb.max_atr_mult == pytest.approx(3.5)
        assert new_config.factors.rel_vol_spike_threshold == pytest.approx(1.7)
        assert new_config.scoring.base_requirement == pytest.approx(1.5)
        assert new_config.trade.t1_r == pytest.approx(1.1)
        assert new_config.trade.runner_r == pytest.approx(2.2)
        
        # Original config unchanged
        assert config.buffer.fixed_ticks == 2
        assert config.trade.t1_r == 1.0

    def test_integer_conversion(self):
        """Test that integer parameters stay integers."""
        config = create_test_config()
        
        optimized_params = {
            'buffer_fixed_ticks': 3.7,  # Float input
        }
        
        new_config = apply_optimized_params(config, optimized_params)
        
        # Should be rounded to integer
        assert new_config.buffer.fixed_ticks == 4
        assert isinstance(new_config.buffer.fixed_ticks, int)


class TestAnalyzeOptimizationResults:
    """Test analyze_optimization_results function."""

    def test_top_trials(self):
        """Test extracting top trials."""
        trials_df = pd.DataFrame([
            {'trial_number': i, 'value': 0.5 - i * 0.05, 
             'expectancy': 0.5, 'win_rate': 0.6, 'total_trades': 10}
            for i in range(20)
        ])
        
        result = OptimizationResult(
            study_name='test',
            best_params={},
            best_value=0.5,
            n_trials=20,
            trials_df=trials_df,
        )
        
        top_trials = analyze_optimization_results(result, top_n=5)
        
        # Should have 5 trials
        assert len(top_trials) == 5
        
        # Should be sorted by value (descending)
        assert top_trials['value'].is_monotonic_decreasing

    def test_empty_results(self):
        """Test with empty results."""
        result = OptimizationResult(
            study_name='test',
            best_params={},
            best_value=0.0,
            n_trials=0,
            trials_df=pd.DataFrame(),
        )
        
        top_trials = analyze_optimization_results(result)
        
        assert top_trials.empty


class TestComputeParameterImportance:
    """Test compute_parameter_importance function."""

    def test_parameter_importance(self):
        """Test parameter importance calculation."""
        # Create trials with correlated parameters
        trials_df = pd.DataFrame([
            {
                'trial_number': i,
                'value': 0.5 + 0.1 * i,  # Increasing
                'param_a': 1.0 + 0.1 * i,  # Correlated
                'param_b': 2.0 - 0.05 * i,  # Anti-correlated
                'param_c': 1.5,  # Constant (uncorrelated)
                'expectancy': 0.5,
            }
            for i in range(10)
        ])
        
        result = OptimizationResult(
            study_name='test',
            best_params={},
            best_value=0.6,
            n_trials=10,
            trials_df=trials_df,
        )
        
        importance_df = compute_parameter_importance(result)
        
        # Should have 3 parameters
        assert len(importance_df) == 3
        
        # param_a should be most important (strongest correlation)
        assert importance_df.iloc[0]['parameter'] == 'param_a'
        
        # Check structure
        assert 'parameter' in importance_df.columns
        assert 'importance' in importance_df.columns
        assert 'correlation' in importance_df.columns


class TestOptimizationResult:
    """Test OptimizationResult dataclass."""

    def test_result_structure(self):
        """Test result dataclass structure."""
        result = OptimizationResult(
            study_name='test_study',
            best_params={'param_a': 1.5, 'param_b': 2.0},
            best_value=0.75,
            n_trials=100,
            trials_df=pd.DataFrame(),
        )
        
        assert result.study_name == 'test_study'
        assert result.best_params == {'param_a': 1.5, 'param_b': 2.0}
        assert result.best_value == 0.75
        assert result.n_trials == 100
