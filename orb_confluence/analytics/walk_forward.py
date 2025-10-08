"""Walk-forward optimization and validation.

Splits data into rolling windows, optimizes on train, validates on test.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from ..backtest.event_loop import EventLoopBacktest
from ..config.schema import StrategyConfig
from .metrics import compute_metrics


@dataclass
class WalkForwardWindow:
    """Single walk-forward window.
    
    Attributes:
        window_id: Window identifier
        train_start: Training start timestamp
        train_end: Training end timestamp
        test_start: Test start timestamp
        test_end: Test end timestamp
        train_bars: Number of bars in training set
        test_bars: Number of bars in test set
    """
    
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_bars: int
    test_bars: int


@dataclass
class WalkForwardResult:
    """Results from walk-forward analysis.
    
    Attributes:
        windows: List of window definitions
        optimization_results: List of optimization results per window
        test_results: List of test results per window
        aggregated_metrics: Overall performance metrics
        stability_metrics: Metrics measuring strategy stability
    """
    
    windows: List[WalkForwardWindow]
    optimization_results: List[dict]
    test_results: List[dict]
    aggregated_metrics: dict
    stability_metrics: dict


def create_walk_forward_windows(
    bars: pd.DataFrame,
    train_bars: int,
    test_bars: int,
    step_bars: Optional[int] = None,
) -> List[WalkForwardWindow]:
    """Create walk-forward train/test windows.
    
    Args:
        bars: Full dataset with timestamp_utc column.
        train_bars: Number of bars in training window.
        test_bars: Number of bars in test window.
        step_bars: Step size between windows (default: test_bars).
        
    Returns:
        List of WalkForwardWindow objects.
        
    Examples:
        >>> windows = create_walk_forward_windows(bars, train_bars=200, test_bars=100)
        >>> for w in windows:
        ...     print(f"Window {w.window_id}: train {w.train_bars} bars, test {w.test_bars} bars")
    """
    if step_bars is None:
        step_bars = test_bars
    
    windows = []
    window_id = 0
    
    total_bars = len(bars)
    current_idx = 0
    
    while current_idx + train_bars + test_bars <= total_bars:
        train_start_idx = current_idx
        train_end_idx = current_idx + train_bars - 1
        test_start_idx = train_end_idx + 1
        test_end_idx = test_start_idx + test_bars - 1
        
        window = WalkForwardWindow(
            window_id=window_id,
            train_start=bars.iloc[train_start_idx]['timestamp_utc'],
            train_end=bars.iloc[train_end_idx]['timestamp_utc'],
            test_start=bars.iloc[test_start_idx]['timestamp_utc'],
            test_end=bars.iloc[test_end_idx]['timestamp_utc'],
            train_bars=train_bars,
            test_bars=test_bars,
        )
        
        windows.append(window)
        window_id += 1
        
        # Move to next window
        current_idx += step_bars
    
    logger.info(f"Created {len(windows)} walk-forward windows")
    
    return windows


def simple_grid_optimization(
    base_config: StrategyConfig,
    train_bars: pd.DataFrame,
    parameter_grid: Dict[str, List[float]],
) -> Tuple[StrategyConfig, float]:
    """Simple grid search optimization.
    
    Args:
        base_config: Base configuration.
        train_bars: Training data.
        parameter_grid: Dictionary of parameter_path -> list of values.
        
    Returns:
        Tuple of (best_config, best_expectancy).
        
    Examples:
        >>> grid = {
        ...     'trade.t1_r': [0.8, 1.0, 1.2],
        ...     'trade.t2_r': [1.3, 1.5, 1.7],
        ... }
        >>> best_config, expectancy = simple_grid_optimization(config, train_bars, grid)
    """
    import copy
    import itertools
    
    best_config = base_config
    best_expectancy = float('-inf')
    
    # Get parameter names and values
    param_names = list(parameter_grid.keys())
    param_values = list(parameter_grid.values())
    
    # Generate all combinations
    combinations = list(itertools.product(*param_values))
    
    logger.info(f"Testing {len(combinations)} parameter combinations")
    
    for combo in combinations:
        # Create config with this combination
        test_config = copy.deepcopy(base_config)
        
        for param_name, param_value in zip(param_names, combo):
            # Navigate to parameter and set value
            parts = param_name.split('.')
            obj = test_config
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], param_value)
        
        # Run backtest
        try:
            engine = EventLoopBacktest(test_config)
            result = engine.run(train_bars)
            metrics = compute_metrics(result.trades)
            expectancy = metrics.expectancy
            
            if expectancy > best_expectancy:
                best_expectancy = expectancy
                best_config = test_config
                logger.debug(f"New best: {combo} → {expectancy:.3f}R")
        
        except Exception as e:
            logger.warning(f"Failed combination {combo}: {e}")
    
    logger.info(f"Best expectancy: {best_expectancy:.3f}R")
    
    return best_config, best_expectancy


def run_walk_forward(
    base_config: StrategyConfig,
    bars: pd.DataFrame,
    train_bars: int,
    test_bars: int,
    parameter_grid: Dict[str, List[float]],
    step_bars: Optional[int] = None,
) -> WalkForwardResult:
    """Run walk-forward optimization and validation.
    
    Args:
        base_config: Base configuration.
        bars: Full dataset.
        train_bars: Training window size.
        test_bars: Test window size.
        parameter_grid: Parameters to optimize.
        step_bars: Step size between windows.
        
    Returns:
        WalkForwardResult with aggregated results.
        
    Examples:
        >>> grid = {'trade.t1_r': [0.8, 1.0, 1.2], 'trade.t2_r': [1.3, 1.5, 1.7]}
        >>> result = run_walk_forward(config, bars, 200, 100, grid)
        >>> print(result.aggregated_metrics)
    """
    # Create windows
    windows = create_walk_forward_windows(bars, train_bars, test_bars, step_bars)
    
    optimization_results = []
    test_results = []
    
    for window in windows:
        logger.info(f"Processing window {window.window_id}")
        
        # Split data
        train_data = bars[
            (bars['timestamp_utc'] >= window.train_start) &
            (bars['timestamp_utc'] <= window.train_end)
        ].copy()
        
        test_data = bars[
            (bars['timestamp_utc'] >= window.test_start) &
            (bars['timestamp_utc'] <= window.test_end)
        ].copy()
        
        # Optimize on train
        best_config, train_expectancy = simple_grid_optimization(
            base_config,
            train_data,
            parameter_grid,
        )
        
        optimization_results.append({
            'window_id': window.window_id,
            'train_expectancy': train_expectancy,
            'train_bars': len(train_data),
        })
        
        # Validate on test
        engine_test = EventLoopBacktest(best_config)
        result_test = engine_test.run(test_data)
        metrics_test = compute_metrics(result_test.trades)
        
        test_results.append({
            'window_id': window.window_id,
            'test_expectancy': metrics_test.expectancy,
            'test_total_r': metrics_test.total_r,
            'test_win_rate': metrics_test.win_rate,
            'test_profit_factor': metrics_test.profit_factor,
            'test_sharpe': metrics_test.sharpe_ratio,
            'test_trades': metrics_test.total_trades,
            'test_bars': len(test_data),
        })
        
        logger.info(
            f"Window {window.window_id}: "
            f"train {train_expectancy:.3f}R → "
            f"test {metrics_test.expectancy:.3f}R "
            f"({metrics_test.total_trades} trades)"
        )
    
    # Aggregate results
    test_df = pd.DataFrame(test_results)
    
    aggregated_metrics = {
        'total_windows': len(windows),
        'avg_test_expectancy': test_df['test_expectancy'].mean(),
        'std_test_expectancy': test_df['test_expectancy'].std(),
        'total_test_r': test_df['test_total_r'].sum(),
        'avg_win_rate': test_df['test_win_rate'].mean(),
        'avg_profit_factor': test_df['test_profit_factor'].mean(),
        'avg_sharpe': test_df['test_sharpe'].mean(),
        'total_trades': test_df['test_trades'].sum(),
    }
    
    # Stability metrics
    stability_metrics = {
        'expectancy_stability': 1.0 / (1.0 + test_df['test_expectancy'].std()),
        'positive_windows': (test_df['test_expectancy'] > 0).sum(),
        'negative_windows': (test_df['test_expectancy'] <= 0).sum(),
        'consistency_ratio': (test_df['test_expectancy'] > 0).mean(),
    }
    
    logger.info(
        f"Walk-forward complete: "
        f"avg expectancy {aggregated_metrics['avg_test_expectancy']:.3f}R, "
        f"consistency {stability_metrics['consistency_ratio']:.1%}"
    )
    
    return WalkForwardResult(
        windows=windows,
        optimization_results=optimization_results,
        test_results=test_results,
        aggregated_metrics=aggregated_metrics,
        stability_metrics=stability_metrics,
    )