"""Regime classification using Gaussian Mixture Models and PCA.

Implements Dr. Hoffman's regime classification methodology from 10_08_project_review.

Regimes:
- TREND: Directional movement with strong commitment
- RANGE: Bounded oscillation with rotation
- VOLATILE: High energy, erratic movement
- TRANSITIONAL: Unclear state, mixed signals
"""

from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.metrics import confusion_matrix, silhouette_score
from loguru import logger


class RegimeClassifier:
    """Regime classifier using GMM with PCA preprocessing.
    
    Uses 8 institutional features to classify market into discrete regimes.
    Follows methodology from 10_08_project_review.md:
    1. Standardize features
    2. PCA dimensionality reduction (85% variance)
    3. Gaussian Mixture Model clustering (4 components)
    4. Map clusters to named regimes
    
    Example:
        >>> from orb_confluence.features.advanced_features import AdvancedFeatures
        >>> from orb_confluence.strategy.regime_classifier import RegimeClassifier
        >>> 
        >>> # Train classifier
        >>> classifier = RegimeClassifier(n_components=4)
        >>> feature_matrix = calculate_historical_features(bars)
        >>> classifier.fit(feature_matrix, expert_labels=expert_regimes)
        >>> 
        >>> # Predict regime
        >>> current_features = calculate_current_features(bars)
        >>> regime = classifier.predict(current_features)
        >>> print(f"Current regime: {regime}")
    """
    
    def __init__(
        self,
        n_components: int = 4,
        pca_variance: float = 0.85,
        random_state: int = 42,
    ):
        """Initialize regime classifier.
        
        Args:
            n_components: Number of regime components (default: 4)
            pca_variance: Minimum variance to retain in PCA (default: 0.85)
            random_state: Random seed for reproducibility
        """
        self.n_components = n_components
        self.pca_variance = pca_variance
        self.random_state = random_state
        
        # Models
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=pca_variance, random_state=random_state)
        self.gmm = GaussianMixture(
            n_components=n_components,
            covariance_type='full',
            random_state=random_state,
            n_init=10,
        )
        
        # Mappings
        self.regime_map: Optional[Dict[int, str]] = None
        self.feature_names: Optional[List[str]] = None
        self.feature_importance: Optional[Dict[str, float]] = None
        
        # Metrics
        self.bic_score: Optional[float] = None
        self.silhouette: Optional[float] = None
        self.confusion_matrix_: Optional[np.ndarray] = None
        
    def fit(
        self,
        X: pd.DataFrame,
        expert_labels: Optional[np.ndarray] = None,
    ) -> 'RegimeClassifier':
        """Train regime classifier on historical data.
        
        Args:
            X: Feature matrix with columns:
                - volatility_term_structure
                - overnight_auction_imbalance
                - rotation_entropy
                - relative_volume_intensity
                - directional_commitment
                - microstructure_pressure
                - intraday_yield_curve
                - composite_liquidity_score
            expert_labels: Optional expert-provided regime labels for supervision
                Should be array of: "TREND", "RANGE", "VOLATILE", "TRANSITIONAL"
                
        Returns:
            self (for method chaining)
        """
        if len(X) < 100:
            raise ValueError(f"Insufficient training data: {len(X)} samples (need at least 100)")
        
        self.feature_names = list(X.columns)
        logger.info(f"Training regime classifier on {len(X)} samples with {len(self.feature_names)} features")
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        logger.debug(f"Feature scaling complete: mean={X_scaled.mean():.3f}, std={X_scaled.std():.3f}")
        
        # Dimensionality reduction with PCA
        X_reduced = self.pca.fit_transform(X_scaled)
        explained_var = np.sum(self.pca.explained_variance_ratio_)
        n_components_retained = X_reduced.shape[1]
        logger.info(
            f"PCA: {n_components_retained} components explain {explained_var:.1%} of variance "
            f"(target: {self.pca_variance:.1%})"
        )
        
        # Fit Gaussian Mixture Model
        logger.info(f"Fitting GMM with {self.n_components} components...")
        self.gmm.fit(X_reduced)
        
        # Calculate BIC score (lower is better)
        self.bic_score = self.gmm.bic(X_reduced)
        logger.info(f"GMM BIC score: {self.bic_score:.2f}")
        
        # Get cluster assignments
        labels = self.gmm.predict(X_reduced)
        
        # Calculate silhouette score (higher is better, range -1 to 1)
        if len(np.unique(labels)) > 1:
            self.silhouette = silhouette_score(X_reduced, labels)
            logger.info(f"Silhouette score: {self.silhouette:.3f}")
        else:
            logger.warning("Only one cluster found, silhouette score not applicable")
            self.silhouette = 0.0
        
        # Map clusters to regime names if expert labels provided
        if expert_labels is not None:
            self.regime_map = self._map_clusters_to_regimes(labels, expert_labels, X)
            
            # Calculate confusion matrix
            predicted_regimes = np.array([self.regime_map[label] for label in labels])
            self.confusion_matrix_ = confusion_matrix(
                expert_labels,
                predicted_regimes,
                labels=["TREND", "RANGE", "VOLATILE", "TRANSITIONAL"]
            )
            
            # Calculate concordance (diagonal sum / total)
            concordance = np.trace(self.confusion_matrix_) / np.sum(self.confusion_matrix_)
            logger.info(f"Expert label concordance: {concordance:.1%}")
            
            if concordance < 0.60:
                logger.warning(
                    f"Low concordance ({concordance:.1%}) with expert labels. "
                    "Consider: 1) More training data, 2) Feature engineering, 3) Different n_components"
                )
        else:
            # No expert labels, create simple mapping based on cluster statistics
            logger.info("No expert labels provided, using statistical mapping")
            self.regime_map = self._statistical_regime_mapping(labels, X_scaled, X)
        
        # Calculate feature importance
        self.feature_importance = self._calculate_feature_importance(X, labels)
        
        logger.info("Regime classifier training complete")
        logger.debug(f"Feature importance: {self.feature_importance}")
        
        return self
    
    def predict(
        self,
        X: pd.DataFrame,
    ) -> np.ndarray:
        """Predict regime for new data.
        
        Args:
            X: Feature matrix with same columns as training data
            
        Returns:
            Array of regime names: "TREND", "RANGE", "VOLATILE", "TRANSITIONAL"
        """
        if self.regime_map is None:
            raise ValueError("Classifier not trained. Call fit() first.")
        
        # Handle single sample (convert to DataFrame if dict)
        if isinstance(X, dict):
            X = pd.DataFrame([X])
        elif isinstance(X, pd.Series):
            X = X.to_frame().T
        
        # Scale and reduce
        X_scaled = self.scaler.transform(X)
        X_reduced = self.pca.transform(X_scaled)
        
        # Predict cluster
        clusters = self.gmm.predict(X_reduced)
        
        # Map to regime names
        regimes = np.array([self.regime_map.get(c, "TRANSITIONAL") for c in clusters])
        
        return regimes
    
    def predict_proba(
        self,
        X: pd.DataFrame,
    ) -> Dict[str, np.ndarray]:
        """Get regime probabilities for new data.
        
        Args:
            X: Feature matrix with same columns as training data
            
        Returns:
            Dictionary mapping regime names to probability arrays
        """
        if self.regime_map is None:
            raise ValueError("Classifier not trained. Call fit() first.")
        
        # Handle single sample
        if isinstance(X, dict):
            X = pd.DataFrame([X])
        elif isinstance(X, pd.Series):
            X = X.to_frame().T
        
        # Scale and reduce
        X_scaled = self.scaler.transform(X)
        X_reduced = self.pca.transform(X_scaled)
        
        # Get cluster probabilities
        cluster_probs = self.gmm.predict_proba(X_reduced)
        
        # Map to regime probabilities
        regime_probs = {}
        for regime in ["TREND", "RANGE", "VOLATILE", "TRANSITIONAL"]:
            # Sum probabilities for all clusters mapped to this regime
            regime_probs[regime] = np.sum(
                cluster_probs[:, [k for k, v in self.regime_map.items() if v == regime]],
                axis=1
            )
        
        return regime_probs
    
    def get_regime_clarity(
        self,
        X: pd.DataFrame,
    ) -> np.ndarray:
        """Calculate regime clarity score (0-1).
        
        High clarity = high confidence in single regime
        Low clarity = mixed/transitional state
        
        Args:
            X: Feature matrix
            
        Returns:
            Clarity scores (0-1) for each sample
        """
        probs = self.predict_proba(X)
        
        # Convert to matrix
        prob_matrix = np.column_stack([
            probs["TREND"],
            probs["RANGE"],
            probs["VOLATILE"],
            probs["TRANSITIONAL"]
        ])
        
        # Clarity = max probability (high = clear, low = mixed)
        clarity = np.max(prob_matrix, axis=1)
        
        return clarity
    
    def _map_clusters_to_regimes(
        self,
        clusters: np.ndarray,
        expert_labels: np.ndarray,
        X: pd.DataFrame,
    ) -> Dict[int, str]:
        """Map cluster numbers to regime names based on expert labels.
        
        Args:
            clusters: Cluster assignments from GMM
            expert_labels: Expert-provided regime labels
            X: Original feature matrix (for logging)
            
        Returns:
            Mapping from cluster ID to regime name
        """
        # Create confusion matrix: rows=expert, cols=clusters
        unique_regimes = ["TREND", "RANGE", "VOLATILE", "TRANSITIONAL"]
        
        # For each cluster, find most common expert label
        cluster_to_regime = {}
        for cluster_id in range(self.n_components):
            cluster_mask = clusters == cluster_id
            if not np.any(cluster_mask):
                logger.warning(f"Cluster {cluster_id} is empty")
                cluster_to_regime[cluster_id] = "TRANSITIONAL"
                continue
            
            # Get expert labels for this cluster
            cluster_expert_labels = expert_labels[cluster_mask]
            
            # Find most common regime
            unique, counts = np.unique(cluster_expert_labels, return_counts=True)
            most_common_regime = unique[np.argmax(counts)]
            cluster_to_regime[cluster_id] = most_common_regime
            
            logger.debug(
                f"Cluster {cluster_id} → {most_common_regime} "
                f"({np.max(counts)}/{len(cluster_expert_labels)} samples)"
            )
        
        return cluster_to_regime
    
    def _statistical_regime_mapping(
        self,
        clusters: np.ndarray,
        X_scaled: np.ndarray,
        X: pd.DataFrame,
    ) -> Dict[int, str]:
        """Map clusters to regimes based on statistical properties.
        
        Without expert labels, use feature statistics to infer regime types.
        
        Args:
            clusters: Cluster assignments
            X_scaled: Scaled feature matrix
            X: Original feature matrix with column names
            
        Returns:
            Mapping from cluster ID to regime name
        """
        cluster_to_regime = {}
        
        for cluster_id in range(self.n_components):
            cluster_mask = clusters == cluster_id
            if not np.any(cluster_mask):
                cluster_to_regime[cluster_id] = "TRANSITIONAL"
                continue
            
            # Get features for this cluster
            cluster_features = X[cluster_mask]
            
            # Calculate key statistics
            avg_directional_commitment = cluster_features['directional_commitment'].mean()
            avg_rotation_entropy = cluster_features['rotation_entropy'].mean()
            avg_volatility_term_structure = cluster_features['volatility_term_structure'].mean()
            avg_yield_curve = cluster_features['intraday_yield_curve'].mean()
            
            # Decision logic
            if avg_directional_commitment > 0.6 and avg_yield_curve < 12:
                regime = "TREND"
            elif avg_rotation_entropy > 0.55 and avg_yield_curve > 12:
                regime = "RANGE"
            elif avg_volatility_term_structure > 1.3:
                regime = "VOLATILE"
            else:
                regime = "TRANSITIONAL"
            
            cluster_to_regime[cluster_id] = regime
            
            logger.debug(
                f"Cluster {cluster_id} → {regime} "
                f"(commitment={avg_directional_commitment:.2f}, "
                f"entropy={avg_rotation_entropy:.2f}, "
                f"vts={avg_volatility_term_structure:.2f})"
            )
        
        return cluster_to_regime
    
    def _calculate_feature_importance(
        self,
        X: pd.DataFrame,
        labels: np.ndarray,
    ) -> Dict[str, float]:
        """Calculate feature importance using ANOVA F-value.
        
        Args:
            X: Feature matrix
            labels: Cluster labels
            
        Returns:
            Dictionary of feature names to importance scores
        """
        from sklearn.feature_selection import f_classif
        
        # Calculate F-values
        F, pval = f_classif(X, labels)
        
        # Create importance dict (normalized)
        importance = dict(zip(X.columns, F / np.sum(F)))
        
        # Sort by importance
        importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
        
        return importance
    
    def get_cluster_centroids(self) -> pd.DataFrame:
        """Get cluster centroids in original feature space.
        
        Returns:
            DataFrame with centroids for each cluster
        """
        if self.regime_map is None:
            raise ValueError("Classifier not trained. Call fit() first.")
        
        # Get centroids in PCA space
        centroids_reduced = self.gmm.means_
        
        # Transform back to scaled feature space
        centroids_scaled = self.pca.inverse_transform(centroids_reduced)
        
        # Transform back to original feature space
        centroids_original = self.scaler.inverse_transform(centroids_scaled)
        
        # Create DataFrame
        df = pd.DataFrame(
            centroids_original,
            columns=self.feature_names,
        )
        df['cluster'] = range(self.n_components)
        df['regime'] = df['cluster'].map(self.regime_map)
        
        return df
    
    def plot_regime_distribution(self, X: pd.DataFrame) -> None:
        """Plot regime distribution in PCA space (for visualization).
        
        Requires matplotlib. Useful for debugging and understanding clusters.
        
        Args:
            X: Feature matrix to visualize
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib not installed, cannot plot")
            return
        
        # Transform to PCA space
        X_scaled = self.scaler.transform(X)
        X_reduced = self.pca.transform(X_scaled)
        
        # Predict regimes
        regimes = self.predict(X)
        
        # Plot first 2 PC components
        fig, ax = plt.subplots(figsize=(10, 8))
        
        colors = {
            "TREND": "blue",
            "RANGE": "green",
            "VOLATILE": "red",
            "TRANSITIONAL": "gray"
        }
        
        for regime in ["TREND", "RANGE", "VOLATILE", "TRANSITIONAL"]:
            mask = regimes == regime
            if np.any(mask):
                ax.scatter(
                    X_reduced[mask, 0],
                    X_reduced[mask, 1],
                    c=colors[regime],
                    label=regime,
                    alpha=0.6,
                    s=50
                )
        
        ax.set_xlabel(f"PC1 ({self.pca.explained_variance_ratio_[0]:.1%} variance)")
        ax.set_ylabel(f"PC2 ({self.pca.explained_variance_ratio_[1]:.1%} variance)")
        ax.set_title("Regime Distribution in PCA Space")
        ax.legend()
        ax.grid(alpha=0.3)
        
        plt.tight_layout()
        plt.show()
    
    def summary(self) -> str:
        """Get summary of classifier performance.
        
        Returns:
            Formatted summary string
        """
        if self.regime_map is None:
            return "Classifier not trained"
        
        lines = [
            "="*60,
            "REGIME CLASSIFIER SUMMARY",
            "="*60,
            f"Components: {self.n_components}",
            f"PCA variance retained: {np.sum(self.pca.explained_variance_ratio_):.1%}",
            f"PCA components: {self.pca.n_components_}",
            f"BIC score: {self.bic_score:.2f}",
            f"Silhouette score: {self.silhouette:.3f}",
            "",
            "Regime Mapping:",
        ]
        
        for cluster_id, regime in sorted(self.regime_map.items()):
            lines.append(f"  Cluster {cluster_id} → {regime}")
        
        if self.confusion_matrix_ is not None:
            concordance = np.trace(self.confusion_matrix_) / np.sum(self.confusion_matrix_)
            lines.append("")
            lines.append(f"Expert concordance: {concordance:.1%}")
        
        lines.append("")
        lines.append("Feature Importance (top 5):")
        if self.feature_importance:
            for i, (feature, importance) in enumerate(list(self.feature_importance.items())[:5]):
                lines.append(f"  {i+1}. {feature}: {importance:.3f}")
        
        lines.append("="*60)
        
        return "\n".join(lines)

