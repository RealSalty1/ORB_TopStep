"""Extension probability models for trade outcome prediction.

Predicts: P(trade reaches target_R before stop)

Features used:
- OR width normalized
- Breakout delay
- Drive energy
- Rotations
- Volume Z-score
- VWAP deviation
- Auction state (one-hot)
- Gap type
- Impulse MFE in first N bars
- Overnight range %
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, brier_score_loss


class ExtensionProbabilityModel(ABC):
    """Abstract base for extension probability models."""
    
    def __init__(self, target_r: float = 1.8, stop_r: float = -1.0) -> None:
        """Initialize model.
        
        Args:
            target_r: Target R-multiple for positive label
            stop_r: Stop R-multiple for negative label
        """
        self.target_r = target_r
        self.stop_r = stop_r
        self.is_fitted = False
        self.feature_names: Optional[List[str]] = None
    
    @abstractmethod
    def fit(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
    ) -> None:
        """Fit model.
        
        Args:
            X: Feature DataFrame
            y: Binary labels (1=reached target, 0=hit stop)
        """
        pass
    
    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Array of probabilities for positive class
        """
        pass
    
    def create_labels(
        self,
        trades_df: pd.DataFrame,
        mfe_col: str = "mfe_r",
        realized_r_col: str = "realized_r",
    ) -> np.ndarray:
        """Create binary labels from trade outcomes.
        
        Label = 1 if MFE >= target_r (reached target before stop)
        Label = 0 otherwise
        
        Args:
            trades_df: DataFrame with trade outcomes
            mfe_col: MFE column name
            realized_r_col: Realized R column name
            
        Returns:
            Binary labels array
        """
        # Label=1 if trade reached target (MFE >= target_r)
        labels = (trades_df[mfe_col] >= self.target_r).astype(int).values
        
        logger.info(
            f"Created labels: {labels.sum()} positive ({labels.mean():.1%}), "
            f"{len(labels) - labels.sum()} negative"
        )
        
        return labels


class LogisticExtensionModel(ExtensionProbabilityModel):
    """Logistic regression extension probability model.
    
    Transparent baseline with interpretable coefficients.
    
    Example:
        >>> model = LogisticExtensionModel(target_r=1.8)
        >>> model.fit(X_train, y_train)
        >>> probs = model.predict_proba(X_test)
    """
    
    def __init__(
        self,
        target_r: float = 1.8,
        stop_r: float = -1.0,
        C: float = 1.0,
        max_iter: int = 1000,
    ) -> None:
        """Initialize logistic model.
        
        Args:
            target_r: Target R-multiple
            stop_r: Stop R-multiple
            C: Inverse regularization strength
            max_iter: Max iterations
        """
        super().__init__(target_r, stop_r)
        self.C = C
        self.max_iter = max_iter
        self.model = LogisticRegression(
            C=C,
            max_iter=max_iter,
            random_state=42,
            solver='lbfgs',
        )
    
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        """Fit logistic model.
        
        Args:
            X: Feature DataFrame
            y: Binary labels
        """
        self.feature_names = list(X.columns)
        
        logger.info(f"Fitting logistic model on {len(X)} samples, {len(X.columns)} features")
        
        self.model.fit(X, y)
        self.is_fitted = True
        
        # Log coefficients
        coef_df = pd.DataFrame({
            'feature': self.feature_names,
            'coefficient': self.model.coef_[0]
        }).sort_values('coefficient', key=abs, ascending=False)
        
        logger.info("Top 5 features by coefficient magnitude:")
        for _, row in coef_df.head(5).iterrows():
            logger.info(f"  {row['feature']}: {row['coefficient']:.4f}")
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Probabilities for positive class
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        # Return probability of positive class (column 1)
        return self.model.predict_proba(X)[:, 1]
    
    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature coefficients.
        
        Returns:
            DataFrame with features and coefficients
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        return pd.DataFrame({
            'feature': self.feature_names,
            'coefficient': self.model.coef_[0],
            'abs_coefficient': np.abs(self.model.coef_[0])
        }).sort_values('abs_coefficient', ascending=False)


class GBDTExtensionModel(ExtensionProbabilityModel):
    """Gradient boosted trees extension probability model.
    
    Captures non-linear interactions between features.
    
    Example:
        >>> model = GBDTExtensionModel(target_r=1.8)
        >>> model.fit(X_train, y_train)
        >>> probs = model.predict_proba(X_test)
    """
    
    def __init__(
        self,
        target_r: float = 1.8,
        stop_r: float = -1.0,
        n_estimators: int = 100,
        max_depth: int = 4,
        learning_rate: float = 0.1,
        min_samples_leaf: int = 20,
    ) -> None:
        """Initialize GBDT model.
        
        Args:
            target_r: Target R-multiple
            stop_r: Stop R-multiple
            n_estimators: Number of boosting stages
            max_depth: Max tree depth
            learning_rate: Boosting learning rate
            min_samples_leaf: Min samples per leaf
        """
        super().__init__(target_r, stop_r)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_samples_leaf = min_samples_leaf
        
        self.model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            min_samples_leaf=min_samples_leaf,
            random_state=42,
            subsample=0.8,
        )
    
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None:
        """Fit GBDT model.
        
        Args:
            X: Feature DataFrame
            y: Binary labels
        """
        self.feature_names = list(X.columns)
        
        logger.info(
            f"Fitting GBDT model on {len(X)} samples, {len(X.columns)} features\n"
            f"  n_estimators={self.n_estimators}, max_depth={self.max_depth}"
        )
        
        self.model.fit(X, y)
        self.is_fitted = True
        
        # Log feature importances
        importance_df = self.get_feature_importance()
        logger.info("Top 5 features by importance:")
        for _, row in importance_df.head(5).iterrows():
            logger.info(f"  {row['feature']}: {row['importance']:.4f}")
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Probabilities for positive class
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        return self.model.predict_proba(X)[:, 1]
    
    def get_feature_importance(self) -> pd.DataFrame:
        """Get feature importances.
        
        Returns:
            DataFrame with features and importances
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        return pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)


def prepare_features_for_model(
    trades_df: pd.DataFrame,
    feature_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Prepare feature matrix for extension model.
    
    Args:
        trades_df: DataFrame with trade data
        feature_cols: Optional list of feature columns to use
        
    Returns:
        Feature DataFrame ready for model
    """
    if feature_cols is None:
        # Default feature set
        feature_cols = [
            'or_width_norm',
            'breakout_delay_minutes',
            'drive_energy',
            'rotations',
            'vol_z',
            'vwap_dev_norm',
            'gap_size_norm',
            'overnight_range_pct',
            'volume_quality_score',
            'normalized_vol',
        ]
        
        # Add auction state one-hot if available
        if 'auction_state' in trades_df.columns:
            auction_dummies = pd.get_dummies(
                trades_df['auction_state'],
                prefix='state',
                drop_first=True
            )
            trades_df = pd.concat([trades_df, auction_dummies], axis=1)
            feature_cols.extend(auction_dummies.columns.tolist())
        
        # Add gap type one-hot if available
        if 'gap_type' in trades_df.columns:
            gap_dummies = pd.get_dummies(
                trades_df['gap_type'],
                prefix='gap',
                drop_first=True
            )
            trades_df = pd.concat([trades_df, gap_dummies], axis=1)
            feature_cols.extend(gap_dummies.columns.tolist())
    
    # Select features that exist
    available_cols = [col for col in feature_cols if col in trades_df.columns]
    
    if len(available_cols) < len(feature_cols):
        missing = set(feature_cols) - set(available_cols)
        logger.warning(f"Missing features: {missing}")
    
    X = trades_df[available_cols].copy()
    
    # Handle missing values
    X = X.fillna(0)
    
    logger.info(f"Prepared feature matrix: {X.shape}")
    
    return X


def train_extension_model(
    trades_df: pd.DataFrame,
    model_type: str = "logistic",
    target_r: float = 1.8,
    test_size: float = 0.2,
    feature_cols: Optional[List[str]] = None,
) -> Tuple[ExtensionProbabilityModel, Dict]:
    """Train and evaluate extension probability model.
    
    Args:
        trades_df: DataFrame with trade outcomes
        model_type: 'logistic' or 'gbdt'
        target_r: Target R-multiple for labeling
        test_size: Test set fraction
        feature_cols: Optional feature column list
        
    Returns:
        Tuple of (fitted_model, metrics_dict)
    """
    # Prepare features
    X = prepare_features_for_model(trades_df, feature_cols)
    
    # Create model
    if model_type == "logistic":
        model = LogisticExtensionModel(target_r=target_r)
    elif model_type == "gbdt":
        model = GBDTExtensionModel(target_r=target_r)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Create labels
    y = model.create_labels(trades_df)
    
    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )
    
    # Fit model
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred_train = model.predict_proba(X_train)
    y_pred_test = model.predict_proba(X_test)
    
    train_auc = roc_auc_score(y_train, y_pred_train)
    test_auc = roc_auc_score(y_test, y_pred_test)
    train_brier = brier_score_loss(y_train, y_pred_train)
    test_brier = brier_score_loss(y_test, y_pred_test)
    
    metrics = {
        'train_auc': train_auc,
        'test_auc': test_auc,
        'train_brier': train_brier,
        'test_brier': test_brier,
        'train_samples': len(y_train),
        'test_samples': len(y_test),
        'positive_rate': y.mean(),
    }
    
    logger.info(f"Model performance:")
    logger.info(f"  Train AUC: {train_auc:.4f}, Brier: {train_brier:.4f}")
    logger.info(f"  Test AUC: {test_auc:.4f}, Brier: {test_brier:.4f}")
    
    return model, metrics

