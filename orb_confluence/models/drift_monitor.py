"""Model drift detection for extension probability models.

Monitors rolling performance and alerts on degradation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.metrics import roc_auc_score, brier_score_loss


@dataclass
class DriftAlert:
    """Model drift alert."""
    
    timestamp: datetime
    metric_name: str
    current_value: float
    baseline_value: float
    threshold_value: float
    alert_type: str  # 'WARNING' or 'CRITICAL'
    message: str
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"DriftAlert({self.alert_type}: {self.metric_name}={self.current_value:.4f} "
            f"vs baseline={self.baseline_value:.4f}, threshold={self.threshold_value:.4f})"
        )


class ModelDriftMonitor:
    """Monitors model performance for drift detection.
    
    Tracks rolling AUC and Brier score, alerts on degradation.
    
    Example:
        >>> monitor = ModelDriftMonitor(
        ...     baseline_auc=0.65,
        ...     baseline_brier=0.18,
        ...     rolling_window=200
        ... )
        >>> 
        >>> # On each new trade
        >>> alert = monitor.update(
        ...     y_true=1,
        ...     y_pred=0.72,
        ...     timestamp=datetime.now()
        ... )
        >>> 
        >>> if alert:
        ...     print(f"Drift detected: {alert}")
    """
    
    def __init__(
        self,
        baseline_auc: float,
        baseline_brier: float,
        rolling_window: int = 200,
        auc_warning_std: float = 1.5,
        auc_critical_std: float = 2.5,
        brier_warning_pct: float = 0.15,
        brier_critical_pct: float = 0.30,
    ) -> None:
        """Initialize drift monitor.
        
        Args:
            baseline_auc: Baseline AUC from training
            baseline_brier: Baseline Brier score from training
            rolling_window: Window size for rolling metrics
            auc_warning_std: Std deviations for AUC warning
            auc_critical_std: Std deviations for AUC critical
            brier_warning_pct: % increase for Brier warning
            brier_critical_pct: % increase for Brier critical
        """
        self.baseline_auc = baseline_auc
        self.baseline_brier = baseline_brier
        self.rolling_window = rolling_window
        
        # Alert thresholds
        self.auc_warning_std = auc_warning_std
        self.auc_critical_std = auc_critical_std
        self.brier_warning_pct = brier_warning_pct
        self.brier_critical_pct = brier_critical_pct
        
        # Rolling data
        self.y_true_history: List[int] = []
        self.y_pred_history: List[float] = []
        self.timestamp_history: List[datetime] = []
        
        # Metrics history
        self.auc_history: List[float] = []
        self.brier_history: List[float] = []
        
        # Alerts
        self.alerts: List[DriftAlert] = []
        
        # Estimate std for AUC (rough approximation)
        self.auc_std_estimate = 0.05  # Will be refined with data
    
    def update(
        self,
        y_true: int,
        y_pred: float,
        timestamp: datetime,
    ) -> Optional[DriftAlert]:
        """Update monitor with new prediction.
        
        Args:
            y_true: True label (0 or 1)
            y_pred: Predicted probability
            timestamp: Prediction timestamp
            
        Returns:
            DriftAlert if drift detected, None otherwise
        """
        # Add to history
        self.y_true_history.append(y_true)
        self.y_pred_history.append(y_pred)
        self.timestamp_history.append(timestamp)
        
        # Keep only rolling window
        if len(self.y_true_history) > self.rolling_window:
            self.y_true_history.pop(0)
            self.y_pred_history.pop(0)
            self.timestamp_history.pop(0)
        
        # Need minimum samples
        if len(self.y_true_history) < 50:
            return None
        
        # Check if we have both classes
        if len(set(self.y_true_history)) < 2:
            return None
        
        # Compute rolling metrics
        try:
            rolling_auc = roc_auc_score(self.y_true_history, self.y_pred_history)
            rolling_brier = brier_score_loss(self.y_true_history, self.y_pred_history)
        except Exception as e:
            logger.warning(f"Error computing rolling metrics: {e}")
            return None
        
        self.auc_history.append(rolling_auc)
        self.brier_history.append(rolling_brier)
        
        # Refine AUC std estimate with data
        if len(self.auc_history) >= 20:
            self.auc_std_estimate = np.std(self.auc_history[-100:])
        
        # Check for drift
        alert = self._check_drift(rolling_auc, rolling_brier, timestamp)
        
        if alert:
            self.alerts.append(alert)
        
        return alert
    
    def _check_drift(
        self,
        current_auc: float,
        current_brier: float,
        timestamp: datetime,
    ) -> Optional[DriftAlert]:
        """Check if drift detected.
        
        Args:
            current_auc: Current rolling AUC
            current_brier: Current rolling Brier
            timestamp: Current timestamp
            
        Returns:
            DriftAlert if drift detected
        """
        # Check AUC degradation
        auc_delta = self.baseline_auc - current_auc
        auc_critical_threshold = self.baseline_auc - (self.auc_critical_std * self.auc_std_estimate)
        auc_warning_threshold = self.baseline_auc - (self.auc_warning_std * self.auc_std_estimate)
        
        if current_auc < auc_critical_threshold:
            return DriftAlert(
                timestamp=timestamp,
                metric_name='AUC',
                current_value=current_auc,
                baseline_value=self.baseline_auc,
                threshold_value=auc_critical_threshold,
                alert_type='CRITICAL',
                message=f'AUC dropped {auc_delta:.4f} below baseline (>{self.auc_critical_std}σ)',
            )
        
        elif current_auc < auc_warning_threshold:
            return DriftAlert(
                timestamp=timestamp,
                metric_name='AUC',
                current_value=current_auc,
                baseline_value=self.baseline_auc,
                threshold_value=auc_warning_threshold,
                alert_type='WARNING',
                message=f'AUC dropped {auc_delta:.4f} below baseline (>{self.auc_warning_std}σ)',
            )
        
        # Check Brier increase
        brier_pct_increase = (current_brier - self.baseline_brier) / self.baseline_brier
        
        if brier_pct_increase > self.brier_critical_pct:
            return DriftAlert(
                timestamp=timestamp,
                metric_name='Brier',
                current_value=current_brier,
                baseline_value=self.baseline_brier,
                threshold_value=self.baseline_brier * (1 + self.brier_critical_pct),
                alert_type='CRITICAL',
                message=f'Brier increased {brier_pct_increase:.1%} above baseline',
            )
        
        elif brier_pct_increase > self.brier_warning_pct:
            return DriftAlert(
                timestamp=timestamp,
                metric_name='Brier',
                current_value=current_brier,
                baseline_value=self.baseline_brier,
                threshold_value=self.baseline_brier * (1 + self.brier_warning_pct),
                alert_type='WARNING',
                message=f'Brier increased {brier_pct_increase:.1%} above baseline',
            )
        
        return None
    
    def get_current_metrics(self) -> dict:
        """Get current rolling metrics.
        
        Returns:
            Dictionary with current metrics
        """
        if len(self.auc_history) == 0:
            return {
                'current_auc': None,
                'current_brier': None,
                'n_samples': len(self.y_true_history),
            }
        
        return {
            'current_auc': self.auc_history[-1],
            'current_brier': self.brier_history[-1],
            'baseline_auc': self.baseline_auc,
            'baseline_brier': self.baseline_brier,
            'n_samples': len(self.y_true_history),
            'n_alerts': len(self.alerts),
        }
    
    def plot_metrics(self, save_path: Optional[str] = None) -> None:
        """Plot rolling metrics over time.
        
        Args:
            save_path: Optional path to save figure
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available, skipping plot")
            return
        
        if len(self.auc_history) < 2:
            logger.warning("Not enough data to plot")
            return
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # AUC plot
        ax1.plot(self.auc_history, label='Rolling AUC')
        ax1.axhline(self.baseline_auc, color='g', linestyle='--', label='Baseline')
        ax1.axhline(
            self.baseline_auc - self.auc_warning_std * self.auc_std_estimate,
            color='orange',
            linestyle=':',
            label='Warning'
        )
        ax1.axhline(
            self.baseline_auc - self.auc_critical_std * self.auc_std_estimate,
            color='r',
            linestyle=':',
            label='Critical'
        )
        ax1.set_ylabel('AUC')
        ax1.set_title('Model Performance: Rolling AUC')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Brier plot
        ax2.plot(self.brier_history, label='Rolling Brier')
        ax2.axhline(self.baseline_brier, color='g', linestyle='--', label='Baseline')
        ax2.axhline(
            self.baseline_brier * (1 + self.brier_warning_pct),
            color='orange',
            linestyle=':',
            label='Warning'
        )
        ax2.axhline(
            self.baseline_brier * (1 + self.brier_critical_pct),
            color='r',
            linestyle=':',
            label='Critical'
        )
        ax2.set_ylabel('Brier Score')
        ax2.set_xlabel('Rolling Window')
        ax2.set_title('Model Performance: Rolling Brier Score')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"Saved metrics plot to {save_path}")
        else:
            plt.show()
        
        plt.close()

