"""Analytics modules for performance analysis.

Includes:
- Performance metrics
- Factor attribution
- Parameter perturbation
- Walk-forward optimization
- Hyperparameter optimization (Optuna)
- Reporting
"""

from .metrics import (
    compute_equity_curve,
    compute_drawdowns,
    compute_metrics,
    PerformanceMetrics,
)
from .attribution import (
    analyze_factor_attribution,
    analyze_score_buckets,
    FactorAttribution,
)
from .perturbation import (
    perturb_config,
    analyze_perturbation,
    run_perturbation_analysis,
    compute_parameter_sensitivity,
    PerturbationResult,
)
from .walk_forward import (
    create_walk_forward_windows,
    simple_grid_optimization,
    run_walk_forward,
    WalkForwardWindow,
    WalkForwardResult,
)
from .optimization import (
    create_objective,
    run_optimization,
    apply_optimized_params,
    analyze_optimization_results,
    compute_parameter_importance,
    OptimizationResult,
)

__all__ = [
    # Metrics
    "compute_equity_curve",
    "compute_drawdowns",
    "compute_metrics",
    "PerformanceMetrics",
    # Attribution
    "analyze_factor_attribution",
    "analyze_score_buckets",
    "FactorAttribution",
    # Perturbation
    "perturb_config",
    "analyze_perturbation",
    "run_perturbation_analysis",
    "compute_parameter_sensitivity",
    "PerturbationResult",
    # Walk-forward
    "create_walk_forward_windows",
    "simple_grid_optimization",
    "run_walk_forward",
    "WalkForwardWindow",
    "WalkForwardResult",
    # Optimization
    "create_objective",
    "run_optimization",
    "apply_optimized_params",
    "analyze_optimization_results",
    "compute_parameter_importance",
    "OptimizationResult",
]