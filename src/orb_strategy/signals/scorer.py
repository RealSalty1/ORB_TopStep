"""Confluence scoring engine.

Aggregates multiple factor signals into weighted scores for long and short
directions. Implements dynamic score thresholds based on trend regime.
"""

from dataclasses import dataclass, field
from typing import Dict

from loguru import logger

from ..config import ScoringConfig, FactorsConfig, ADXConfig
from ..features.factors import (
    FactorIndicator,
    RelativeVolumeIndicator,
    PriceActionIndicator,
    ProfileProxyIndicator,
    VWAPIndicator,
    ADXIndicator,
    FactorSignal,
)
import pandas as pd


@dataclass
class ConfluenceScore:
    """Confluence score result."""

    long_score: float
    short_score: float
    
    long_pass: bool
    short_pass: bool
    
    factor_signals: Dict[str, FactorSignal] = field(default_factory=dict)
    
    # Metadata
    required_score: float = 0.0
    is_weak_trend: bool = False


class ConfluenceScorer:
    """Confluence scoring engine.

    Computes weighted scores from multiple factors and applies scoring gates.
    """

    def __init__(
        self,
        scoring_config: ScoringConfig,
        factors_config: FactorsConfig,
    ) -> None:
        """Initialize confluence scorer.

        Args:
            scoring_config: Scoring configuration.
            factors_config: Factor configurations.
        """
        self.scoring_config = scoring_config
        self.factors_config = factors_config

        # Initialize factor indicators
        self.factors: Dict[str, FactorIndicator] = {}

        if factors_config.rel_volume.enabled:
            self.factors["rel_vol"] = RelativeVolumeIndicator(factors_config.rel_volume)

        if factors_config.price_action.enabled:
            self.factors["price_action"] = PriceActionIndicator(factors_config.price_action)

        if factors_config.profile_proxy.enabled:
            self.factors["profile"] = ProfileProxyIndicator(factors_config.profile_proxy)

        if factors_config.vwap.enabled:
            self.factors["vwap"] = VWAPIndicator(factors_config.vwap)

        if factors_config.adx.enabled:
            self.factors["adx"] = ADXIndicator(factors_config.adx)

        logger.info(f"Initialized confluence scorer with {len(self.factors)} factors")

    def score(self, df: pd.DataFrame, bar_idx: int) -> ConfluenceScore:
        """Compute confluence score for a bar.

        Args:
            df: DataFrame with bar data.
            bar_idx: Index of bar to score.

        Returns:
            ConfluenceScore with weighted scores and factor details.
        """
        # Compute all factor signals
        factor_signals: Dict[str, FactorSignal] = {}

        for factor_name, factor in self.factors.items():
            try:
                signal = factor.calculate(df, bar_idx)
                factor_signals[factor_name] = signal
            except Exception as e:
                logger.warning(f"Factor {factor_name} calculation failed at bar {bar_idx}: {e}")
                # Use neutral signal on failure
                factor_signals[factor_name] = FactorSignal(
                    long_signal=False,
                    short_signal=False,
                )

        # Compute weighted scores
        long_score = 0.0
        short_score = 0.0

        weights = self.scoring_config.weights

        for factor_name, signal in factor_signals.items():
            weight = weights.get(factor_name, 1.0)

            if signal.long_signal:
                long_score += weight

            if signal.short_signal:
                short_score += weight

        # Determine required score based on trend regime
        is_weak_trend = self._is_weak_trend(factor_signals)

        if is_weak_trend:
            required_score = self.scoring_config.weak_trend_required
        else:
            required_score = self.scoring_config.base_required

        # Check if scores pass threshold
        long_pass = long_score >= required_score if self.scoring_config.enabled else True
        short_pass = short_score >= required_score if self.scoring_config.enabled else True

        return ConfluenceScore(
            long_score=long_score,
            short_score=short_score,
            long_pass=long_pass,
            short_pass=short_pass,
            factor_signals=factor_signals,
            required_score=required_score,
            is_weak_trend=is_weak_trend,
        )

    def _is_weak_trend(self, factor_signals: Dict[str, FactorSignal]) -> bool:
        """Determine if current regime is weak trend.

        Args:
            factor_signals: Dict of factor signals.

        Returns:
            True if trend is weak (ADX below threshold or ADX not enabled).
        """
        if not self.factors_config.adx.enabled:
            # If ADX not enabled, treat as weak trend (more conservative)
            return True

        adx_signal = factor_signals.get("adx")

        if adx_signal is None or adx_signal.value is None:
            return True

        # Weak trend if ADX below threshold
        return adx_signal.value < self.factors_config.adx.threshold
