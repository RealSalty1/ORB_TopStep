"""Probability modeling modules for ORB 2.0.

Includes:
- Extension probability models (logistic, GBDT)
- Model calibration
- Drift detection
- Feature engineering for models
"""

from .extension_model import (
    ExtensionProbabilityModel,
    LogisticExtensionModel,
    GBDTExtensionModel,
)
from .calibration import (
    CalibratedModel,
    calibrate_probabilities,
    compute_brier_score,
    plot_reliability_curve,
)
from .drift_monitor import (
    ModelDriftMonitor,
    DriftAlert,
)

__all__ = [
    "ExtensionProbabilityModel",
    "LogisticExtensionModel",
    "GBDTExtensionModel",
    "CalibratedModel",
    "calibrate_probabilities",
    "compute_brier_score",
    "plot_reliability_curve",
    "ModelDriftMonitor",
    "DriftAlert",
]

