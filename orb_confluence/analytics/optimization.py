"""Hyperparameter optimization using Optuna.

Provides systematic parameter search with multi-objective optimization.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import optuna
import pandas as pd
from loguru import logger

from ..backtest.event_loop import EventLoopBacktest
from ..config.schema import StrategyConfig
from .metrics import compute_metrics


@dataclass
class OptimizationResult:
    """Results from optimization run.
    
    Attributes:
        study_name: Name of the optimization study
        best_params: Best parameters found
        best_value: Best objective value
        n_trials: Number of trials completed
        trials_df: DataFrame with all trial results
    """
    
    study_name: str
    best_params: Dict[str, float]
    best_value: float
    n_trials: int
    trials_df: pd.DataFrame


def create_objective(
    base_config: StrategyConfig,
    bars: pd.DataFrame,
    expectancy_weight: float = 1.0,
    drawdown_penalty: float = 0.3,
    min_trades: int = 5,
) -> Callable:
    """Create objective function for Optuna optimization.
    
    Args:
        base_config: Base configuration to modify.
        bars: Market data for backtesting.
        expectancy_weight: Weight for expectancy in composite score.
        drawdown_penalty: Penalty multiplier for drawdown.
        min_trades: Minimum trades required (else penalty).
        
    Returns:
        Objective function for Optuna.
        
    Examples:
        >>> objective = create_objective(config, bars)
        >>> study = optuna.create_study(direction='maximize')
        >>> study.optimize(objective, n_trials=100)
    """
    import copy
    
    def objective(trial: optuna.Trial) -> float:
        """Objective function for single trial.
        
        Args:
            trial: Optuna trial object.
            
        Returns:
            Composite score (higher is better).
        """
        # Sample parameters
        buffer_fixed_ticks = trial.suggest_int('buffer_fixed_ticks', 1, 5)
        
        min_atr_mult = trial.suggest_float('min_atr_mult', 0.2, 0.5, step=0.05)
        max_atr_mult = trial.suggest_float('max_atr_mult', 2.0, 4.0, step=0.5)
        
        rel_vol_spike = trial.suggest_float('rel_vol_spike_threshold', 1.2, 2.0, step=0.1)
        
        score_base_req = trial.suggest_float('scoring_base_requirement', 0.5, 2.0, step=0.25)
        score_weak_req = trial.suggest_float('scoring_weak_requirement', 1.5, 3.0, step=0.25)
        
        t1_r = trial.suggest_float('trade_t1_r', 0.8, 1.2, step=0.1)
        t2_r = trial.suggest_float('trade_t2_r', 1.2, 1.8, step=0.1)
        runner_r = trial.suggest_float('trade_runner_r', 1.5, 2.5, step=0.25)
        
        # Ensure constraints
        if max_atr_mult <= min_atr_mult:
            max_atr_mult = min_atr_mult + 1.0
        
        if score_weak_req <= score_base_req:
            score_weak_req = score_base_req + 0.5
        
        if t2_r <= t1_r:
            t2_r = t1_r + 0.2
        
        if runner_r <= t2_r:
            runner_r = t2_r + 0.3
        
        # Create modified config
        trial_config = copy.deepcopy(base_config)
        
        trial_config.buffer.fixed_ticks = buffer_fixed_ticks
        trial_config.orb.min_atr_mult = min_atr_mult
        trial_config.orb.max_atr_mult = max_atr_mult
        trial_config.factors.rel_vol_spike_threshold = rel_vol_spike
        trial_config.scoring.base_requirement = score_base_req
        trial_config.scoring.weak_trend_requirement = score_weak_req
        trial_config.trade.t1_r = t1_r
        trial_config.trade.t2_r = t2_r
        trial_config.trade.runner_r = runner_r
        
        # Run backtest
        try:
            engine = EventLoopBacktest(trial_config)
            result = engine.run(bars)
            metrics = compute_metrics(result.trades)
            
            # Check minimum trades
            if metrics.total_trades < min_trades:
                penalty = (min_trades - metrics.total_trades) * 0.5
                return -penalty
            
            # Compute composite score
            expectancy_score = metrics.expectancy * expectancy_weight
            drawdown_score = metrics.max_drawdown_r * drawdown_penalty  # Negative value
            
            composite = expectancy_score + drawdown_score  # drawdown_score is negative
            
            # Log trial
            trial.set_user_attr('expectancy', metrics.expectancy)
            trial.set_user_attr('total_trades', metrics.total_trades)
            trial.set_user_attr('win_rate', metrics.win_rate)
            trial.set_user_attr('max_drawdown_r', metrics.max_drawdown_r)
            trial.set_user_attr('sharpe_ratio', metrics.sharpe_ratio)
            
            logger.debug(
                f"Trial {trial.number}: composite={composite:.3f} "
                f"(exp={metrics.expectancy:.3f}, dd={metrics.max_drawdown_r:.2f}, "
                f"trades={metrics.total_trades})"
            )
            
            return composite
        
        except Exception as e:
            logger.warning(f"Trial {trial.number} failed: {e}")
            return -999.0  # Large penalty for failed trials
    
    return objective


def run_optimization(
    base_config: StrategyConfig,
    bars: pd.DataFrame,
    n_trials: int = 100,
    study_name: str = 'orb_optimization',
    expectancy_weight: float = 1.0,
    drawdown_penalty: float = 0.3,
    min_trades: int = 5,
    n_jobs: int = 1,
) -> OptimizationResult:
    """Run Optuna optimization.
    
    Args:
        base_config: Base configuration.
        bars: Market data.
        n_trials: Number of trials to run.
        study_name: Name for the study.
        expectancy_weight: Weight for expectancy.
        drawdown_penalty: Penalty for drawdown.
        min_trades: Minimum trades required.
        n_jobs: Number of parallel jobs (1 = sequential).
        
    Returns:
        OptimizationResult with best parameters and trial history.
        
    Examples:
        >>> result = run_optimization(config, bars, n_trials=100)
        >>> print(f"Best params: {result.best_params}")
        >>> print(f"Best score: {result.best_value:.3f}")
        >>> print(result.trials_df.head())
    """
    logger.info(f"Starting optimization: {n_trials} trials")
    
    # Create objective
    objective = create_objective(
        base_config,
        bars,
        expectancy_weight,
        drawdown_penalty,
        min_trades,
    )
    
    # Create study
    study = optuna.create_study(
        study_name=study_name,
        direction='maximize',
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    
    # Optimize
    study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs, show_progress_bar=True)
    
    # Extract results
    best_params = study.best_params
    best_value = study.best_value
    
    logger.info(f"Optimization complete: best value = {best_value:.3f}")
    logger.info(f"Best params: {best_params}")
    
    # Build trials DataFrame
    trials_data = []
    for trial in study.trials:
        if trial.state == optuna.trial.TrialState.COMPLETE:
            record = {
                'trial_number': trial.number,
                'value': trial.value,
                **trial.params,
                **trial.user_attrs,
            }
            trials_data.append(record)
    
    trials_df = pd.DataFrame(trials_data)
    
    return OptimizationResult(
        study_name=study_name,
        best_params=best_params,
        best_value=best_value,
        n_trials=len(study.trials),
        trials_df=trials_df,
    )


def apply_optimized_params(
    base_config: StrategyConfig,
    optimized_params: Dict[str, float],
) -> StrategyConfig:
    """Apply optimized parameters to config.
    
    Args:
        base_config: Base configuration.
        optimized_params: Parameters from optimization.
        
    Returns:
        New config with optimized parameters.
        
    Examples:
        >>> result = run_optimization(config, bars)
        >>> optimized_config = apply_optimized_params(config, result.best_params)
    """
    import copy
    
    new_config = copy.deepcopy(base_config)
    
    # Map parameter names to config paths
    param_mapping = {
        'buffer_fixed_ticks': ('buffer', 'fixed_ticks'),
        'min_atr_mult': ('orb', 'min_atr_mult'),
        'max_atr_mult': ('orb', 'max_atr_mult'),
        'rel_vol_spike_threshold': ('factors', 'rel_vol_spike_threshold'),
        'scoring_base_requirement': ('scoring', 'base_requirement'),
        'scoring_weak_requirement': ('scoring', 'weak_trend_requirement'),
        'trade_t1_r': ('trade', 't1_r'),
        'trade_t2_r': ('trade', 't2_r'),
        'trade_runner_r': ('trade', 'runner_r'),
    }
    
    for param_name, value in optimized_params.items():
        if param_name in param_mapping:
            section, attr = param_mapping[param_name]
            obj = getattr(new_config, section)
            
            # Convert to int if original was int
            original_value = getattr(obj, attr)
            if isinstance(original_value, int):
                value = int(round(value))
            
            setattr(obj, attr, value)
    
    return new_config


def analyze_optimization_results(
    result: OptimizationResult,
    top_n: int = 10,
) -> pd.DataFrame:
    """Analyze optimization results.
    
    Args:
        result: Optimization result.
        top_n: Number of top trials to return.
        
    Returns:
        DataFrame with top trials and statistics.
        
    Examples:
        >>> result = run_optimization(config, bars)
        >>> top_trials = analyze_optimization_results(result, top_n=10)
        >>> print(top_trials[['value', 'expectancy', 'win_rate', 'total_trades']])
    """
    if result.trials_df.empty:
        return pd.DataFrame()
    
    # Sort by value (composite score)
    sorted_df = result.trials_df.sort_values('value', ascending=False)
    
    # Return top N
    top_df = sorted_df.head(top_n).copy()
    
    return top_df


def compute_parameter_importance(
    result: OptimizationResult,
) -> pd.DataFrame:
    """Compute parameter importance from optimization.
    
    Uses Optuna's importance analyzer.
    
    Args:
        result: Optimization result.
        
    Returns:
        DataFrame with parameter importance scores.
        
    Examples:
        >>> result = run_optimization(config, bars)
        >>> importance = compute_parameter_importance(result)
        >>> print(importance.sort_values('importance', ascending=False))
    """
    # Would need access to study object for this
    # For now, return correlation-based importance
    
    if result.trials_df.empty:
        return pd.DataFrame()
    
    # Get parameter columns
    param_cols = [col for col in result.trials_df.columns 
                  if col not in ['trial_number', 'value', 'expectancy', 
                                'total_trades', 'win_rate', 'max_drawdown_r', 
                                'sharpe_ratio']]
    
    # Compute correlation with objective value
    importances = []
    for param in param_cols:
        corr = result.trials_df[param].corr(result.trials_df['value'])
        importances.append({
            'parameter': param,
            'importance': abs(corr),
            'correlation': corr,
        })
    
    importance_df = pd.DataFrame(importances)
    importance_df = importance_df.sort_values('importance', ascending=False)
    
    return importance_df
