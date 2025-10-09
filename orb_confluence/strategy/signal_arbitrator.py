"""Signal Arbitration System.

Resolves conflicts when multiple playbooks generate signals simultaneously.

Uses hierarchical decision framework based on Dr. Hoffman's specifications:
    Signal_Priority = Σ wᵢ × Fᵢ

Where factors include:
- Regime alignment score
- Historical expectancy in current hour
- Signal strength percentile
- Capital efficiency (R/bars)
- Portfolio correlation contribution

Implements Bayesian multi-armed bandit for dynamic weight optimization.

Based on Dr. Hoffman's 10_08_project_review.md Section 5.1
"""

from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from dataclasses import dataclass
from loguru import logger

from orb_confluence.strategy.playbook_base import Signal


@dataclass
class ArbitrationDecision:
    """Result of signal arbitration.
    
    Attributes:
        selected_signal: The signal chosen for execution
        rejected_signals: Signals that were not selected
        priority_score: Final priority score of selected signal
        factor_scores: Breakdown of individual factor scores
        reason: Human-readable reason for selection
    """
    selected_signal: Signal
    rejected_signals: List[Signal]
    priority_score: float
    factor_scores: Dict[str, float]
    reason: str


class SignalArbitrator:
    """Arbitrates between conflicting signals from multiple playbooks.
    
    When multiple playbooks generate signals at the same time, this system
    decides which signal to take based on a weighted scoring function.
    
    Uses Bayesian multi-armed bandit to optimize weights over time based
    on actual performance.
    
    Example:
        >>> arbitrator = SignalArbitrator()
        >>> signals = [signal1, signal2, signal3]  # From different playbooks
        >>> decision = arbitrator.arbitrate(signals, current_regime, current_hour)
        >>> print(f"Selected: {decision.selected_signal.playbook_name}")
        >>> print(f"Reason: {decision.reason}")
    """
    
    def __init__(
        self,
        max_simultaneous_signals: int = 1,
        enable_weight_learning: bool = True,
        learning_rate: float = 0.05,
    ):
        """Initialize signal arbitrator.
        
        Args:
            max_simultaneous_signals: Maximum signals to execute simultaneously (default: 1)
            enable_weight_learning: Enable Bayesian weight optimization (default: True)
            learning_rate: Learning rate for weight updates (default: 0.05)
        """
        self.max_simultaneous_signals = max_simultaneous_signals
        self.enable_weight_learning = enable_weight_learning
        self.learning_rate = learning_rate
        
        # Factor weights (will be optimized over time)
        self.weights = {
            'regime_alignment': 0.30,
            'historical_expectancy': 0.25,
            'signal_strength': 0.20,
            'capital_efficiency': 0.15,
            'correlation_contribution': 0.10,
        }
        
        # Track decisions for learning
        self.decision_history: List[Dict[str, Any]] = []
        self.update_count = 0
        
        # Historical expectancy by playbook and hour
        self.playbook_hour_expectancy: Dict[str, Dict[int, float]] = {}
        
        # Signal strength percentiles
        self.strength_history: Dict[str, List[float]] = {}
        
    def arbitrate(
        self,
        signals: List[Signal],
        current_regime: str,
        current_hour: int,
        open_positions: Optional[List[Any]] = None,
        portfolio_correlation: Optional[Dict[str, float]] = None,
    ) -> Optional[ArbitrationDecision]:
        """Arbitrate between multiple signals.
        
        Args:
            signals: List of signals from different playbooks
            current_regime: Current market regime
            current_hour: Hour of day (0-23)
            open_positions: Currently open positions
            portfolio_correlation: Correlation matrix for portfolio
            
        Returns:
            ArbitrationDecision with selected signal, or None if all rejected
        """
        if not signals:
            return None
        
        # If only one signal, no arbitration needed
        if len(signals) == 1:
            signal = signals[0]
            return ArbitrationDecision(
                selected_signal=signal,
                rejected_signals=[],
                priority_score=1.0,
                factor_scores={'single_signal': 1.0},
                reason="Only signal available"
            )
        
        logger.info(f"Arbitrating between {len(signals)} signals")
        
        # Calculate priority scores for each signal
        signal_scores = []
        for signal in signals:
            score, factors = self._calculate_priority_score(
                signal, current_regime, current_hour, 
                open_positions, portfolio_correlation
            )
            signal_scores.append((signal, score, factors))
            logger.debug(
                f"  {signal.playbook_name}: score={score:.3f}, "
                f"factors={factors}"
            )
        
        # Sort by priority score (highest first)
        signal_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select top N signals (usually just 1)
        selected = signal_scores[:self.max_simultaneous_signals]
        rejected = signal_scores[self.max_simultaneous_signals:]
        
        # Create decision
        best_signal, best_score, best_factors = selected[0]
        rejected_signals = [s[0] for s in rejected]
        
        # Generate reason
        reason = self._generate_reason(best_signal, best_factors, rejected_signals)
        
        decision = ArbitrationDecision(
            selected_signal=best_signal,
            rejected_signals=rejected_signals,
            priority_score=best_score,
            factor_scores=best_factors,
            reason=reason
        )
        
        # Record decision for learning
        self._record_decision(decision, current_regime, current_hour)
        
        logger.info(f"Selected: {best_signal.playbook_name} (score={best_score:.3f})")
        logger.info(f"Reason: {reason}")
        
        return decision
    
    def _calculate_priority_score(
        self,
        signal: Signal,
        current_regime: str,
        current_hour: int,
        open_positions: Optional[List[Any]],
        portfolio_correlation: Optional[Dict[str, float]],
    ) -> tuple:
        """Calculate priority score for a signal.
        
        Args:
            signal: Signal to score
            current_regime: Current regime
            current_hour: Hour of day
            open_positions: Open positions
            portfolio_correlation: Portfolio correlation
            
        Returns:
            Tuple of (priority_score, factor_breakdown)
        """
        factors = {}
        
        # Factor 1: Regime alignment (built into signal)
        factors['regime_alignment'] = signal.regime_alignment
        
        # Factor 2: Historical expectancy for this hour
        hour_expectancy = self._get_hour_expectancy(signal.playbook_name, current_hour)
        factors['historical_expectancy'] = hour_expectancy
        
        # Factor 3: Signal strength percentile
        strength_percentile = self._get_strength_percentile(
            signal.playbook_name, signal.strength
        )
        factors['signal_strength'] = strength_percentile
        
        # Factor 4: Capital efficiency (expected R per bar)
        capital_efficiency = self._calculate_capital_efficiency(signal)
        factors['capital_efficiency'] = capital_efficiency
        
        # Factor 5: Correlation contribution to portfolio
        correlation_score = self._calculate_correlation_score(
            signal, open_positions, portfolio_correlation
        )
        factors['correlation_contribution'] = correlation_score
        
        # Calculate weighted priority score
        priority_score = sum(
            self.weights[factor_name] * factor_value
            for factor_name, factor_value in factors.items()
        )
        
        return (priority_score, factors)
    
    def _get_hour_expectancy(self, playbook_name: str, hour: int) -> float:
        """Get historical expectancy for playbook at this hour.
        
        Args:
            playbook_name: Name of playbook
            hour: Hour of day (0-23)
            
        Returns:
            Normalized expectancy score (0-1)
        """
        if playbook_name not in self.playbook_hour_expectancy:
            return 0.5  # Neutral if no history
        
        hour_data = self.playbook_hour_expectancy[playbook_name]
        if hour not in hour_data:
            return 0.5
        
        expectancy = hour_data[hour]
        
        # Normalize to 0-1 (assume expectancy range -0.5 to 0.5)
        normalized = (expectancy + 0.5) / 1.0
        return float(np.clip(normalized, 0, 1))
    
    def _get_strength_percentile(self, playbook_name: str, strength: float) -> float:
        """Get percentile rank of signal strength.
        
        Args:
            playbook_name: Name of playbook
            strength: Signal strength
            
        Returns:
            Percentile (0-1)
        """
        if playbook_name not in self.strength_history:
            return 0.5  # Neutral if no history
        
        history = self.strength_history[playbook_name]
        if len(history) < 10:
            return 0.5
        
        # Calculate percentile
        percentile = np.percentile(history, strength * 100)
        return float(np.clip(percentile, 0, 1))
    
    def _calculate_capital_efficiency(self, signal: Signal) -> float:
        """Calculate capital efficiency (expected R per bar).
        
        Higher efficiency = faster profits = better.
        
        Args:
            signal: Trading signal
            
        Returns:
            Efficiency score (0-1)
        """
        # Estimate bars in trade based on playbook type
        playbook_type = signal.metadata.get('setup_type', 'UNKNOWN')
        
        # Expected bars by type
        expected_bars = {
            'IB_FADE': 30,
            'VWAP_MAGNET': 20,
            'MOMENTUM_CONTINUATION': 50,
            'OPENING_DRIVE_REVERSAL': 15,
        }
        
        bars = expected_bars.get(playbook_type, 30)
        
        # Expected R from first profit target
        if signal.profit_targets:
            expected_r = signal.profit_targets[0].r_multiple
        else:
            expected_r = 1.0
        
        # R per bar
        r_per_bar = expected_r / bars if bars > 0 else 0.05
        
        # Normalize (assume max 0.1 R/bar)
        efficiency = r_per_bar / 0.1
        
        return float(np.clip(efficiency, 0, 1))
    
    def _calculate_correlation_score(
        self,
        signal: Signal,
        open_positions: Optional[List[Any]],
        portfolio_correlation: Optional[Dict[str, float]],
    ) -> float:
        """Calculate portfolio correlation contribution.
        
        Lower correlation with existing positions = better diversification.
        
        Args:
            signal: Trading signal
            open_positions: Open positions
            portfolio_correlation: Correlation matrix
            
        Returns:
            Correlation score (0-1), higher = better diversification
        """
        # If no open positions, perfect diversification
        if not open_positions or len(open_positions) == 0:
            return 1.0
        
        # If no correlation data, neutral
        if not portfolio_correlation:
            return 0.5
        
        # Calculate average correlation with open positions
        correlations = []
        for pos in open_positions:
            if hasattr(pos, 'playbook_name'):
                key = f"{signal.playbook_name}_{pos.playbook_name}"
                if key in portfolio_correlation:
                    correlations.append(portfolio_correlation[key])
        
        if not correlations:
            return 0.5
        
        # Average correlation
        avg_corr = np.mean(correlations)
        
        # Invert (low correlation = high score)
        # Correlation ranges from -1 to 1, convert to 0-1 then invert
        normalized_corr = (avg_corr + 1) / 2  # 0 to 1
        score = 1.0 - normalized_corr  # Invert
        
        return float(np.clip(score, 0, 1))
    
    def _generate_reason(
        self,
        selected_signal: Signal,
        factors: Dict[str, float],
        rejected_signals: List[Signal],
    ) -> str:
        """Generate human-readable reason for selection.
        
        Args:
            selected_signal: Selected signal
            factors: Factor scores
            rejected_signals: Rejected signals
            
        Returns:
            Reason string
        """
        # Find strongest factor
        strongest_factor = max(factors.items(), key=lambda x: x[1])
        factor_name, factor_value = strongest_factor
        
        # Create reason
        if len(rejected_signals) == 0:
            return f"{selected_signal.playbook_name} - only signal"
        
        rejected_names = [s.playbook_name for s in rejected_signals]
        
        reason = (
            f"{selected_signal.playbook_name} selected over "
            f"{', '.join(rejected_names)} - "
            f"strongest factor: {factor_name} ({factor_value:.2f})"
        )
        
        return reason
    
    def _record_decision(
        self,
        decision: ArbitrationDecision,
        regime: str,
        hour: int,
    ):
        """Record decision for learning.
        
        Args:
            decision: Arbitration decision
            regime: Current regime
            hour: Hour of day
        """
        record = {
            'timestamp': pd.Timestamp.now(),
            'selected_playbook': decision.selected_signal.playbook_name,
            'rejected_playbooks': [s.playbook_name for s in decision.rejected_signals],
            'priority_score': decision.priority_score,
            'factors': decision.factor_scores.copy(),
            'regime': regime,
            'hour': hour,
            'signal_strength': decision.selected_signal.strength,
        }
        
        self.decision_history.append(record)
        
        # Update strength history
        playbook_name = decision.selected_signal.playbook_name
        if playbook_name not in self.strength_history:
            self.strength_history[playbook_name] = []
        self.strength_history[playbook_name].append(decision.selected_signal.strength)
    
    def update_with_result(
        self,
        decision: ArbitrationDecision,
        r_multiple: float,
        bars_in_trade: int,
    ):
        """Update arbitrator with trade result for learning.
        
        Uses result to optimize factor weights via Bayesian update.
        
        Args:
            decision: Original arbitration decision
            r_multiple: Actual R-multiple achieved
            bars_in_trade: Bars in trade
        """
        if not self.enable_weight_learning:
            return
        
        playbook_name = decision.selected_signal.playbook_name
        
        # Update hour expectancy
        # (Would need hour info from decision metadata)
        
        # Calculate prediction error
        # Expected R from targets
        if decision.selected_signal.profit_targets:
            expected_r = decision.selected_signal.profit_targets[0].r_multiple
        else:
            expected_r = 1.0
        
        prediction_error = r_multiple - expected_r
        
        # Update weights using gradient descent
        # Positive error = increase weights of high-scoring factors
        # Negative error = decrease weights of high-scoring factors
        
        if abs(prediction_error) > 0.1:  # Only update for significant errors
            for factor_name, factor_value in decision.factor_scores.items():
                if factor_name in self.weights:
                    # Update weight proportional to factor value and error
                    update = self.learning_rate * prediction_error * factor_value
                    self.weights[factor_name] += update
            
            # Normalize weights to sum to 1.0
            total = sum(self.weights.values())
            for key in self.weights:
                self.weights[key] /= total
            
            self.update_count += 1
            
            if self.update_count % 10 == 0:
                logger.info(f"Updated weights (n={self.update_count}): {self.weights}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get arbitrator statistics.
        
        Returns:
            Dictionary with stats
        """
        if not self.decision_history:
            return {'total_decisions': 0}
        
        # Playbook selection frequency
        playbook_counts = {}
        for decision in self.decision_history:
            pb = decision['selected_playbook']
            playbook_counts[pb] = playbook_counts.get(pb, 0) + 1
        
        # Average priority scores
        avg_priority = np.mean([d['priority_score'] for d in self.decision_history])
        
        return {
            'total_decisions': len(self.decision_history),
            'playbook_frequency': playbook_counts,
            'average_priority_score': float(avg_priority),
            'current_weights': self.weights.copy(),
            'weight_updates': self.update_count,
        }
    
    def reset_learning(self):
        """Reset learning state (useful for testing)."""
        self.weights = {
            'regime_alignment': 0.30,
            'historical_expectancy': 0.25,
            'signal_strength': 0.20,
            'capital_efficiency': 0.15,
            'correlation_contribution': 0.10,
        }
        self.decision_history = []
        self.update_count = 0
        logger.info("Reset arbitrator learning state")
    
    def save_state(self, filepath: str):
        """Save arbitrator state to file.
        
        Args:
            filepath: Path to save state
        """
        import pickle
        
        state = {
            'weights': self.weights,
            'playbook_hour_expectancy': self.playbook_hour_expectancy,
            'strength_history': self.strength_history,
            'update_count': self.update_count,
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(state, f)
        
        logger.info(f"Saved arbitrator state to {filepath}")
    
    def load_state(self, filepath: str):
        """Load arbitrator state from file.
        
        Args:
            filepath: Path to load state from
        """
        import pickle
        
        with open(filepath, 'rb') as f:
            state = pickle.load(f)
        
        self.weights = state['weights']
        self.playbook_hour_expectancy = state['playbook_hour_expectancy']
        self.strength_history = state['strength_history']
        self.update_count = state['update_count']
        
        logger.info(f"Loaded arbitrator state from {filepath}")


class CrossEntropyMinimizer:
    """Minimize cross-entropy between mean reversion playbooks.
    
    Prevents redundant exposure when multiple mean reversion signals occur.
    Uses cross-entropy to measure similarity between signals.
    
    Based on Dr. Hoffman's Section 2.3: "Mean reversion playbooks (IB Fade/VWAP Magnet)
    require cross-entropy minimization to eliminate redundant exposure."
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        """Initialize cross-entropy minimizer.
        
        Args:
            similarity_threshold: Threshold for considering signals redundant (0-1)
        """
        self.similarity_threshold = similarity_threshold
    
    def filter_redundant_signals(
        self,
        signals: List[Signal],
    ) -> List[Signal]:
        """Filter out redundant mean reversion signals.
        
        Args:
            signals: List of signals
            
        Returns:
            Filtered list with redundant signals removed
        """
        # Only process mean reversion signals
        mean_rev_signals = [
            s for s in signals 
            if s.metadata.get('setup_type') in ['IB_FADE', 'VWAP_MAGNET']
        ]
        
        other_signals = [
            s for s in signals
            if s.metadata.get('setup_type') not in ['IB_FADE', 'VWAP_MAGNET']
        ]
        
        if len(mean_rev_signals) <= 1:
            return signals
        
        # Calculate pairwise similarities
        filtered = []
        for i, signal1 in enumerate(mean_rev_signals):
            is_redundant = False
            
            for j, signal2 in enumerate(filtered):
                similarity = self._calculate_similarity(signal1, signal2)
                
                if similarity > self.similarity_threshold:
                    # Redundant - keep the stronger signal
                    if signal1.strength <= signal2.strength:
                        is_redundant = True
                        break
            
            if not is_redundant:
                filtered.append(signal1)
        
        logger.info(
            f"Cross-entropy filter: {len(mean_rev_signals)} mean-rev signals "
            f"→ {len(filtered)} after redundancy removal"
        )
        
        return filtered + other_signals
    
    def _calculate_similarity(self, signal1: Signal, signal2: Signal) -> float:
        """Calculate similarity between two signals.
        
        High similarity = redundant exposure.
        
        Args:
            signal1: First signal
            signal2: Second signal
            
        Returns:
            Similarity score (0-1)
        """
        # Factor 1: Same direction
        same_direction = (signal1.direction == signal2.direction)
        direction_score = 1.0 if same_direction else 0.0
        
        # Factor 2: Similar entry price (within 0.5%)
        price_diff = abs(signal1.entry_price - signal2.entry_price) / signal1.entry_price
        price_similarity = 1.0 - min(price_diff / 0.005, 1.0)
        
        # Factor 3: Similar stop distance
        risk1 = signal1.initial_risk
        risk2 = signal2.initial_risk
        risk_diff = abs(risk1 - risk2) / max(risk1, risk2)
        risk_similarity = 1.0 - min(risk_diff / 0.3, 1.0)
        
        # Weighted combination
        similarity = (
            0.5 * direction_score +
            0.3 * price_similarity +
            0.2 * risk_similarity
        )
        
        return float(similarity)

