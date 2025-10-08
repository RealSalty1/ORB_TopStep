"""Probability calibration for extension models.

Uses isotonic regression to calibrate predicted probabilities
to match observed frequencies.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss


@dataclass
class CalibrationMetrics:
    """Calibration quality metrics."""
    
    brier_score: float
    brier_score_calibrated: float
    calibration_bins: int
    max_bin_error: float
    mean_abs_error: float
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"Calibration(Brier: {self.brier_score:.4f} → {self.brier_score_calibrated:.4f}, "
            f"max_bin_err={self.max_bin_error:.4f})"
        )


class CalibratedModel:
    """Wrapper for calibrated probability model.
    
    Applies isotonic regression to calibrate probabilities.
    
    Example:
        >>> base_model = LogisticExtensionModel()
        >>> base_model.fit(X_train, y_train)
        >>> 
        >>> calibrated = CalibratedModel(base_model)
        >>> calibrated.fit(X_val, y_val)
        >>> 
        >>> probs_calibrated = calibrated.predict_proba(X_test)
    """
    
    def __init__(
        self,
        base_model,
        out_of_bounds: str = 'clip',
    ) -> None:
        """Initialize calibrated model.
        
        Args:
            base_model: Base model with predict_proba method
            out_of_bounds: How to handle OOB predictions ('clip' or 'nan')
        """
        self.base_model = base_model
        self.calibrator = IsotonicRegression(out_of_bounds=out_of_bounds)
        self.is_calibrated = False
    
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        """Fit calibration on validation set.
        
        Args:
            X: Feature DataFrame
            y: True labels
        """
        # Get base model predictions
        y_pred_uncalibrated = self.base_model.predict_proba(X)
        
        # Fit isotonic regression
        self.calibrator.fit(y_pred_uncalibrated, y)
        self.is_calibrated = True
        
        # Compute metrics
        y_pred_calibrated = self.calibrator.predict(y_pred_uncalibrated)
        
        brier_before = brier_score_loss(y, y_pred_uncalibrated)
        brier_after = brier_score_loss(y, y_pred_calibrated)
        
        logger.info(
            f"Calibration fitted: Brier {brier_before:.4f} → {brier_after:.4f}"
        )
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict calibrated probabilities.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Calibrated probabilities
        """
        if not self.is_calibrated:
            raise ValueError("Model not calibrated, call fit() first")
        
        # Get base predictions
        y_pred_uncalibrated = self.base_model.predict_proba(X)
        
        # Apply calibration
        y_pred_calibrated = self.calibrator.predict(y_pred_uncalibrated)
        
        return y_pred_calibrated


def calibrate_probabilities(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Tuple[np.ndarray, IsotonicRegression]:
    """Calibrate probabilities using isotonic regression.
    
    Args:
        y_true: True binary labels
        y_pred: Predicted probabilities
        
    Returns:
        Tuple of (calibrated_probs, calibrator)
    """
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(y_pred, y_true)
    
    y_pred_calibrated = calibrator.predict(y_pred)
    
    return y_pred_calibrated, calibrator


def compute_brier_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """Compute Brier score.
    
    Args:
        y_true: True binary labels
        y_pred: Predicted probabilities
        
    Returns:
        Brier score (lower is better)
    """
    return brier_score_loss(y_true, y_pred)


def compute_calibration_curve(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bins: int = 10,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute calibration curve (reliability diagram data).
    
    Args:
        y_true: True binary labels
        y_pred: Predicted probabilities
        n_bins: Number of bins for bucketing
        
    Returns:
        Tuple of (bin_centers, observed_frequencies, bin_counts)
    """
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_pred, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)
    
    bin_centers = (bins[:-1] + bins[1:]) / 2
    observed_frequencies = np.zeros(n_bins)
    bin_counts = np.zeros(n_bins)
    
    for i in range(n_bins):
        mask = bin_indices == i
        bin_counts[i] = mask.sum()
        
        if bin_counts[i] > 0:
            observed_frequencies[i] = y_true[mask].mean()
        else:
            observed_frequencies[i] = np.nan
    
    return bin_centers, observed_frequencies, bin_counts


def plot_reliability_curve(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_pred_calibrated: Optional[np.ndarray] = None,
    n_bins: int = 10,
    save_path: Optional[str] = None,
) -> None:
    """Plot reliability (calibration) curve.
    
    Args:
        y_true: True binary labels
        y_pred: Predicted probabilities (uncalibrated)
        y_pred_calibrated: Optional calibrated probabilities
        n_bins: Number of bins
        save_path: Optional path to save figure
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available, skipping plot")
        return
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Plot perfect calibration line
    ax.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
    
    # Plot uncalibrated
    bin_centers, obs_freq, bin_counts = compute_calibration_curve(
        y_true, y_pred, n_bins
    )
    valid_mask = ~np.isnan(obs_freq)
    ax.plot(
        bin_centers[valid_mask],
        obs_freq[valid_mask],
        'o-',
        label=f'Uncalibrated (Brier={compute_brier_score(y_true, y_pred):.4f})',
        markersize=8
    )
    
    # Plot calibrated if provided
    if y_pred_calibrated is not None:
        bin_centers_cal, obs_freq_cal, _ = compute_calibration_curve(
            y_true, y_pred_calibrated, n_bins
        )
        valid_mask_cal = ~np.isnan(obs_freq_cal)
        ax.plot(
            bin_centers_cal[valid_mask_cal],
            obs_freq_cal[valid_mask_cal],
            's-',
            label=f'Calibrated (Brier={compute_brier_score(y_true, y_pred_calibrated):.4f})',
            markersize=8
        )
    
    ax.set_xlabel('Predicted Probability', fontsize=12)
    ax.set_ylabel('Observed Frequency', fontsize=12)
    ax.set_title('Probability Calibration (Reliability Curve)', fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Saved reliability curve to {save_path}")
    else:
        plt.show()
    
    plt.close()


def evaluate_calibration(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_pred_calibrated: Optional[np.ndarray] = None,
    n_bins: int = 10,
) -> CalibrationMetrics:
    """Evaluate calibration quality.
    
    Args:
        y_true: True binary labels
        y_pred: Predicted probabilities
        y_pred_calibrated: Optional calibrated probabilities
        n_bins: Number of bins
        
    Returns:
        CalibrationMetrics
    """
    # Compute Brier scores
    brier_uncalibrated = compute_brier_score(y_true, y_pred)
    
    if y_pred_calibrated is not None:
        brier_calibrated = compute_brier_score(y_true, y_pred_calibrated)
        probs_to_eval = y_pred_calibrated
    else:
        brier_calibrated = brier_uncalibrated
        probs_to_eval = y_pred
    
    # Compute calibration curve
    bin_centers, obs_freq, bin_counts = compute_calibration_curve(
        y_true, probs_to_eval, n_bins
    )
    
    # Compute errors (only for bins with data)
    valid_mask = ~np.isnan(obs_freq)
    if valid_mask.sum() > 0:
        bin_errors = np.abs(obs_freq[valid_mask] - bin_centers[valid_mask])
        max_bin_error = bin_errors.max()
        mean_abs_error = bin_errors.mean()
    else:
        max_bin_error = 0.0
        mean_abs_error = 0.0
    
    return CalibrationMetrics(
        brier_score=brier_uncalibrated,
        brier_score_calibrated=brier_calibrated,
        calibration_bins=n_bins,
        max_bin_error=max_bin_error,
        mean_abs_error=mean_abs_error,
    )

