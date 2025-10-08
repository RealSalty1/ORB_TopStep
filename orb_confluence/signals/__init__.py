"""Signal generation and filtering modules for ORB 2.0.

Includes:
- Probability gating
- Runner activation logic
- Signal filtering and prioritization
"""

from .probability_gate import (
    ProbabilityGate,
    ProbabilityGateConfig,
    SignalWithProbability,
    apply_probability_gate,
)

__all__ = [
    "ProbabilityGate",
    "ProbabilityGateConfig",
    "SignalWithProbability",
    "apply_probability_gate",
]

