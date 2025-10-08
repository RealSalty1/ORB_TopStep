"""Parameter perturbation analysis for sensitivity testing.

Tests strategy robustness by varying parameters and measuring performance changes.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from ..backtest.event_loop import EventLoopBacktest, BacktestResult
from ..config.schema import StrategyConfig
from .metrics import compute_metrics


@dataclass
class PerturbationResult:
    """Result of parameter perturbation analysis.
    
    Attributes:
        parameter_name: Name of perturbed parameter
        base_value: Original parameter value
        perturbed_value: New parameter value
        delta_pct: Percentage change applied
        base_expectancy: Expectancy with base config
        perturbed_expectancy: Expectancy with perturbed config
        expectancy_change: Absolute change in expectancy
        expectancy_change_pct: Percentage change in expectancy
    """
    
    parameter_name: str
    base_value: float
    perturbed_value: float
    delta_pct: float
    base_expectancy: float
    perturbed_expectancy: float
    expectancy_change: float
    expectancy_change_pct: float


def perturb_config(
    base_config: StrategyConfig,
    parameter_path: str,
    delta_pct: float,
) -> StrategyConfig:
    """Create perturbed config with parameter adjusted by delta %.
    
    Args:
        base_config: Base configuration.
        parameter_path: Dot-separated path to parameter (e.g., 'trade.t1_r').
        delta_pct: Percentage change (e.g., 10.0 for +10%).
        
    Returns:
        New config with perturbed parameter.
        
    Examples:
        >>> new_config = perturb_config(config, 'trade.t1_r', 10.0)
        >>> # If base t1_r was 1.0, new is 1.1
    """
    import copy
    
    # Deep copy config
    new_config = copy.deepcopy(base_config)
    
    # Parse path
    parts = parameter_path.split('.')
    
    # Navigate to parameter
    obj = new_config
    for part in parts[:-1]:
        obj = getattr(obj, part)
    
    # Get base value
    param_name = parts[-1]
    base_value = getattr(obj, param_name)
    
    # Calculate new value
    if isinstance(base_value, (int, float)):
        multiplier = 1.0 + (delta_pct / 100.0)
        new_value = base_value * multiplier
        
        # Preserve type
        if isinstance(base_value, int):
            new_value = int(round(new_value))
        
        setattr(obj, param_name, new_value)
    else:
        raise ValueError(f"Cannot perturb non-numeric parameter: {parameter_path}")
    
    return new_config


def analyze_perturbation(
    base_config: StrategyConfig,
    bars: pd.DataFrame,
    parameter_path: str,
    delta_pct: float,
) -> PerturbationResult:
    """Analyze impact of perturbing a single parameter.
    
    Args:
        base_config: Base configuration.
        bars: Market data.
        parameter_path: Dot-separated path to parameter.
        delta_pct: Percentage change.
        
    Returns:
        PerturbationResult with expectancy comparison.
        
    Examples:
        >>> result = analyze_perturbation(config, bars, 'trade.t1_r', 10.0)
        >>> print(f"Expectancy change: {result.expectancy_change:.3f}R")
    """
    # Run base backtest
    engine_base = EventLoopBacktest(base_config)
    result_base = engine_base.run(bars)
    metrics_base = compute_metrics(result_base.trades)
    base_expectancy = metrics_base.expectancy
    
    # Get base value
    parts = parameter_path.split('.')
    obj = base_config
    for part in parts[:-1]:
        obj = getattr(obj, part)
    base_value = getattr(obj, parts[-1])
    
    # Create perturbed config
    perturbed_config = perturb_config(base_config, parameter_path, delta_pct)
    
    # Get perturbed value
    obj_pert = perturbed_config
    for part in parts[:-1]:
        obj_pert = getattr(obj_pert, part)
    perturbed_value = getattr(obj_pert, parts[-1])
    
    # Run perturbed backtest
    engine_pert = EventLoopBacktest(perturbed_config)
    result_pert = engine_pert.run(bars)
    metrics_pert = compute_metrics(result_pert.trades)
    perturbed_expectancy = metrics_pert.expectancy
    
    # Calculate changes
    expectancy_change = perturbed_expectancy - base_expectancy
    expectancy_change_pct = (expectancy_change / base_expectancy * 100) if base_expectancy != 0 else 0.0
    
    logger.info(
        f"Perturbation {parameter_path} {delta_pct:+.0f}%: "
        f"{base_value} → {perturbed_value}, "
        f"expectancy {base_expectancy:.3f} → {perturbed_expectancy:.3f} "
        f"({expectancy_change:+.3f}R, {expectancy_change_pct:+.1f}%)"
    )
    
    return PerturbationResult(
        parameter_name=parameter_path,
        base_value=float(base_value),
        perturbed_value=float(perturbed_value),
        delta_pct=delta_pct,
        base_expectancy=base_expectancy,
        perturbed_expectancy=perturbed_expectancy,
        expectancy_change=expectancy_change,
        expectancy_change_pct=expectancy_change_pct,
    )


def run_perturbation_analysis(
    base_config: StrategyConfig,
    bars: pd.DataFrame,
    parameters: List[str],
    delta_pcts: List[float] = [-20, -10, 10, 20],
) -> pd.DataFrame:
    """Run perturbation analysis on multiple parameters.
    
    Args:
        base_config: Base configuration.
        bars: Market data.
        parameters: List of parameter paths to perturb.
        delta_pcts: List of percentage changes to test.
        
    Returns:
        DataFrame with perturbation results.
        
    Examples:
        >>> params = ['trade.t1_r', 'trade.t2_r', 'trade.runner_r']
        >>> results_df = run_perturbation_analysis(config, bars, params)
        >>> print(results_df[['parameter_name', 'delta_pct', 'expectancy_change']])
    """
    results = []
    
    for param in parameters:
        for delta in delta_pcts:
            try:
                result = analyze_perturbation(base_config, bars, param, delta)
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to perturb {param} by {delta}%: {e}")
    
    if not results:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame([
        {
            'parameter_name': r.parameter_name,
            'base_value': r.base_value,
            'perturbed_value': r.perturbed_value,
            'delta_pct': r.delta_pct,
            'base_expectancy': r.base_expectancy,
            'perturbed_expectancy': r.perturbed_expectancy,
            'expectancy_change': r.expectancy_change,
            'expectancy_change_pct': r.expectancy_change_pct,
        }
        for r in results
    ])
    
    return df


def compute_parameter_sensitivity(perturbation_df: pd.DataFrame) -> pd.DataFrame:
    """Compute sensitivity metrics for each parameter.
    
    Args:
        perturbation_df: Output from run_perturbation_analysis.
        
    Returns:
        DataFrame with sensitivity metrics per parameter.
        
    Examples:
        >>> sensitivity = compute_parameter_sensitivity(perturbation_df)
        >>> print(sensitivity.sort_values('avg_abs_change', ascending=False))
    """
    if perturbation_df.empty:
        return pd.DataFrame()
    
    # Group by parameter
    grouped = perturbation_df.groupby('parameter_name')
    
    sensitivity = grouped.agg({
        'expectancy_change': ['mean', 'std'],
        'expectancy_change_pct': ['mean', 'std'],
    }).reset_index()
    
    # Flatten column names
    sensitivity.columns = [
        'parameter_name',
        'avg_expectancy_change',
        'std_expectancy_change',
        'avg_expectancy_change_pct',
        'std_expectancy_change_pct',
    ]
    
    # Add absolute average change
    abs_changes = perturbation_df.groupby('parameter_name')['expectancy_change'].apply(
        lambda x: x.abs().mean()
    ).reset_index()
    abs_changes.columns = ['parameter_name', 'avg_abs_change']
    
    sensitivity = sensitivity.merge(abs_changes, on='parameter_name')
    
    # Sort by sensitivity (largest absolute average change)
    sensitivity = sensitivity.sort_values('avg_abs_change', ascending=False)
    
    return sensitivity