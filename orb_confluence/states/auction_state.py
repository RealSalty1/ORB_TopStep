"""Auction state classification for opening range analysis.

Classifies OR period into states:
- INITIATIVE: Strong directional drive with low rotations
- BALANCED: High rotations, balanced participation
- COMPRESSION: Narrow range, low energy
- GAP_REV: Gap failing to extend (reversion setup)
- INVENTORY_FIX: Overnight inventory correction
- MIXED: Ambiguous or no clear state
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import numpy as np
from loguru import logger

from orb_confluence.features.auction_metrics import AuctionMetrics, GapType
from orb_confluence.features.or_layers import DualORState


class AuctionState(str, Enum):
    """Auction state classification."""
    INITIATIVE = "INITIATIVE"  # Strong directional drive
    BALANCED = "BALANCED"  # Two-sided, rotational
    COMPRESSION = "COMPRESSION"  # Narrow, low energy
    GAP_REV = "GAP_REV"  # Gap reversion setup
    INVENTORY_FIX = "INVENTORY_FIX"  # Overnight correction
    MIXED = "MIXED"  # Ambiguous


@dataclass
class StateClassification:
    """Auction state classification result."""
    
    state: AuctionState
    confidence: float  # 0-1
    state_scores: Dict[AuctionState, float]  # Score for each state
    reason: str  # Explanation
    
    def __repr__(self) -> str:
        """String representation."""
        return f"StateClassification({self.state.value}, conf={self.confidence:.2f}, reason='{self.reason}')"


class AuctionStateClassifier:
    """Rule-based auction state classifier (v1).
    
    Uses heuristics on auction metrics to classify OR state.
    
    Configuration thresholds:
    - drive_energy_threshold: Min drive for INITIATIVE
    - rotations_initiative_max: Max rotations for INITIATIVE
    - compression_width_threshold: Max width_norm for COMPRESSION
    - volume_z_initiative: Min volume Z for INITIATIVE
    - gap_size_threshold: Min gap size for GAP_REV consideration
    
    Example:
        >>> classifier = AuctionStateClassifier()
        >>> classification = classifier.classify(
        ...     auction_metrics=metrics,
        ...     dual_or=or_state
        ... )
        >>> print(classification.state)
    """
    
    def __init__(
        self,
        drive_energy_threshold: float = 0.55,
        rotations_initiative_max: int = 2,
        compression_width_percentile: float = 0.20,
        volume_z_initiative: float = 1.0,
        gap_size_threshold: float = 0.5,  # ATR multiples
        balanced_rotations_min: int = 3,
        inventory_bias_threshold: float = 0.6,
    ) -> None:
        """Initialize classifier with thresholds.
        
        Args:
            drive_energy_threshold: Min drive energy for INITIATIVE
            rotations_initiative_max: Max rotations for INITIATIVE
            compression_width_percentile: Width percentile threshold for COMPRESSION
            volume_z_initiative: Min volume Z-score for INITIATIVE
            gap_size_threshold: Min gap size (ATR) for GAP_REV
            balanced_rotations_min: Min rotations for BALANCED
            inventory_bias_threshold: Min inventory bias for INVENTORY_FIX
        """
        self.drive_threshold = drive_energy_threshold
        self.rotations_max = rotations_initiative_max
        self.compression_width_pct = compression_width_percentile
        self.vol_z_threshold = volume_z_initiative
        self.gap_threshold = gap_size_threshold
        self.balanced_rotations = balanced_rotations_min
        self.inventory_threshold = inventory_bias_threshold
    
    def classify(
        self,
        auction_metrics: AuctionMetrics,
        dual_or: DualORState,
    ) -> StateClassification:
        """Classify auction state.
        
        Args:
            auction_metrics: Computed auction metrics
            dual_or: Dual OR state
            
        Returns:
            StateClassification with state and confidence
        """
        # Compute scores for each state
        scores = {}
        
        # INITIATIVE score
        scores[AuctionState.INITIATIVE] = self._score_initiative(auction_metrics)
        
        # COMPRESSION score
        scores[AuctionState.COMPRESSION] = self._score_compression(
            auction_metrics, dual_or
        )
        
        # GAP_REV score
        scores[AuctionState.GAP_REV] = self._score_gap_reversion(auction_metrics)
        
        # BALANCED score
        scores[AuctionState.BALANCED] = self._score_balanced(auction_metrics)
        
        # INVENTORY_FIX score
        scores[AuctionState.INVENTORY_FIX] = self._score_inventory_fix(auction_metrics)
        
        # Select highest score
        max_state = max(scores, key=scores.get)
        max_score = scores[max_state]
        
        # If max score below threshold, classify as MIXED
        if max_score < 0.5:
            state = AuctionState.MIXED
            confidence = 1.0 - max_score  # Inverse confidence
            reason = "No clear state pattern"
        else:
            state = max_state
            # Normalize confidence (softmax-style)
            confidence = self._compute_confidence(scores, max_state)
            reason = self._generate_reason(state, auction_metrics, dual_or)
        
        logger.debug(
            f"Classified state: {state.value} (conf={confidence:.2f}) - {reason}"
        )
        
        return StateClassification(
            state=state,
            confidence=confidence,
            state_scores=scores,
            reason=reason,
        )
    
    def _score_initiative(self, metrics: AuctionMetrics) -> float:
        """Score INITIATIVE state.
        
        Args:
            metrics: Auction metrics
            
        Returns:
            Score 0-1
        """
        score = 0.0
        
        # High drive energy
        if metrics.drive_energy >= self.drive_threshold:
            score += 0.4
        else:
            score += metrics.drive_energy / self.drive_threshold * 0.4
        
        # Low rotations
        if metrics.rotations <= self.rotations_max:
            score += 0.3
        else:
            penalty = (metrics.rotations - self.rotations_max) * 0.1
            score += max(0, 0.3 - penalty)
        
        # Volume participation
        if metrics.volume_z >= self.vol_z_threshold:
            score += 0.3
        elif metrics.volume_z > 0:
            score += metrics.volume_z / self.vol_z_threshold * 0.3
        
        return min(score, 1.0)
    
    def _score_compression(
        self,
        metrics: AuctionMetrics,
        dual_or: DualORState,
    ) -> float:
        """Score COMPRESSION state.
        
        Args:
            metrics: Auction metrics
            dual_or: Dual OR state
            
        Returns:
            Score 0-1
        """
        score = 0.0
        
        # Narrow width (use primary width norm)
        if dual_or.primary_width_norm is not None:
            # Assume compression_width_pct represents target normalized width
            # E.g., if width_norm < 0.5, strong compression
            compression_target = 0.5
            if dual_or.primary_width_norm <= compression_target:
                score += 0.5
            else:
                # Decay score as width increases
                score += max(0, 0.5 * (1 - (dual_or.primary_width_norm - compression_target)))
        
        # Low drive energy
        if metrics.drive_energy <= 0.3:
            score += 0.3
        else:
            score += max(0, 0.3 * (1 - metrics.drive_energy))
        
        # Low volume
        if metrics.volume_z < 0:
            score += 0.2
        
        return min(score, 1.0)
    
    def _score_gap_reversion(self, metrics: AuctionMetrics) -> float:
        """Score GAP_REV state.
        
        Args:
            metrics: Auction metrics
            
        Returns:
            Score 0-1
        """
        # Must have significant gap
        if metrics.gap_type not in [GapType.FULL_UP, GapType.FULL_DOWN]:
            return 0.0
        
        if metrics.gap_size_norm < self.gap_threshold:
            return 0.0
        
        score = 0.0
        
        # Large gap
        if metrics.gap_size_norm >= self.gap_threshold:
            score += 0.5
        
        # Failure to extend (high wick ratio indicates rejection)
        if metrics.max_wick_ratio > 1.0:
            score += 0.3
        
        # Low drive (gap not extending)
        if metrics.drive_energy < 0.4:
            score += 0.2
        
        return min(score, 1.0)
    
    def _score_balanced(self, metrics: AuctionMetrics) -> float:
        """Score BALANCED state.
        
        Args:
            metrics: Auction metrics
            
        Returns:
            Score 0-1
        """
        score = 0.0
        
        # High rotations
        if metrics.rotations >= self.balanced_rotations:
            score += 0.5
        else:
            score += metrics.rotations / self.balanced_rotations * 0.5
        
        # Moderate volume (not spike, not dead)
        if 0.8 <= metrics.volume_ratio <= 1.3:
            score += 0.3
        
        # Moderate drive (not trending, not dead)
        if 0.3 <= metrics.drive_energy <= 0.6:
            score += 0.2
        
        return min(score, 1.0)
    
    def _score_inventory_fix(self, metrics: AuctionMetrics) -> float:
        """Score INVENTORY_FIX state.
        
        Args:
            metrics: Auction metrics
            
        Returns:
            Score 0-1
        """
        score = 0.0
        
        # Strong overnight inventory bias
        if abs(metrics.overnight_inventory_bias) >= self.inventory_threshold:
            score += 0.5
        
        # Open opposite to overnight bias (correction)
        # If overnight was long-biased and open is below, that's a fix
        if abs(metrics.open_vs_prior_mid) > 0.3:
            # Check if direction is opposite to overnight bias
            if metrics.open_vs_prior_mid * metrics.overnight_inventory_bias < 0:
                score += 0.3
        
        # Moderate drive (some correction movement)
        if 0.3 <= metrics.drive_energy <= 0.7:
            score += 0.2
        
        return min(score, 1.0)
    
    def _compute_confidence(
        self,
        scores: Dict[AuctionState, float],
        selected_state: AuctionState,
    ) -> float:
        """Compute confidence via softmax-style normalization.
        
        Args:
            scores: State scores
            selected_state: Selected state
            
        Returns:
            Confidence 0-1
        """
        # Softmax with temperature
        temperature = 2.0
        exp_scores = {s: np.exp(score / temperature) for s, score in scores.items()}
        total = sum(exp_scores.values())
        
        if total > 0:
            confidence = exp_scores[selected_state] / total
        else:
            confidence = 0.5
        
        return confidence
    
    def _generate_reason(
        self,
        state: AuctionState,
        metrics: AuctionMetrics,
        dual_or: DualORState,
    ) -> str:
        """Generate human-readable reason for classification.
        
        Args:
            state: Classified state
            metrics: Auction metrics
            dual_or: Dual OR state
            
        Returns:
            Reason string
        """
        if state == AuctionState.INITIATIVE:
            return (
                f"Strong drive_energy={metrics.drive_energy:.2f}, "
                f"low rotations={metrics.rotations}, "
                f"vol_z={metrics.volume_z:.2f}"
            )
        elif state == AuctionState.COMPRESSION:
            return (
                f"Narrow width_norm={dual_or.primary_width_norm:.2f}, "
                f"low drive={metrics.drive_energy:.2f}"
            )
        elif state == AuctionState.GAP_REV:
            return (
                f"Gap {metrics.gap_type.value} size={metrics.gap_size_norm:.2f}ATR, "
                f"failing to extend"
            )
        elif state == AuctionState.BALANCED:
            return (
                f"High rotations={metrics.rotations}, "
                f"balanced volume_ratio={metrics.volume_ratio:.2f}"
            )
        elif state == AuctionState.INVENTORY_FIX:
            return (
                f"Overnight bias={metrics.overnight_inventory_bias:.2f}, "
                f"correcting at open"
            )
        else:
            return "No clear state pattern"


def classify_auction_state(
    auction_metrics: AuctionMetrics,
    dual_or: DualORState,
    config: Optional[Dict] = None,
) -> StateClassification:
    """Convenience function to classify auction state.
    
    Args:
        auction_metrics: Computed auction metrics
        dual_or: Dual OR state
        config: Optional config dict with thresholds
        
    Returns:
        StateClassification
    """
    if config is None:
        classifier = AuctionStateClassifier()
    else:
        classifier = AuctionStateClassifier(**config)
    
    return classifier.classify(auction_metrics, dual_or)

