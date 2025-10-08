"""Probability gating for signal filtering and runner activation.

Uses extension probability (p_extension) to:
1. Filter low-probability signals (hard floor)
2. Reduce size on medium probabilities (soft floor)
3. Enable runner mode on high probabilities
4. Adjust exit targets based on probability

Logic:
- p < p_min_floor: Reject signal
- p_min_floor <= p < p_soft_floor: Reduce size (e.g., 50%)
- p >= p_soft_floor: Full size
- p >= p_runner_threshold: Enable runner mode
"""

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from ..playbooks.base import CandidateSignal


@dataclass
class ProbabilityGateConfig:
    """Configuration for probability gating."""
    
    # Floor thresholds
    p_min_floor: float = 0.35  # Min probability to trade
    p_soft_floor: float = 0.45  # Full size above this
    
    # Runner threshold
    p_runner_threshold: float = 0.55  # Enable runner above this
    
    # Size adjustments
    reduced_size_factor: float = 0.5  # Reduction factor for soft floor
    
    # Exit adjustments
    adjust_targets_by_prob: bool = True  # Adjust targets based on prob
    high_prob_target_mult: float = 1.3  # Increase targets for high prob
    low_prob_target_mult: float = 0.8  # Decrease targets for low prob
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"ProbabilityGate(min={self.p_min_floor:.2f}, "
            f"soft={self.p_soft_floor:.2f}, "
            f"runner={self.p_runner_threshold:.2f})"
        )


@dataclass
class SignalWithProbability:
    """Signal with probability assessment."""
    
    signal: CandidateSignal
    p_extension: float
    passed_gate: bool
    rejection_reason: Optional[str] = None
    size_adjustment: float = 1.0
    runner_enabled: bool = False
    target_adjustment: float = 1.0
    
    def __repr__(self) -> str:
        """String representation."""
        status = "PASS" if self.passed_gate else "REJECT"
        return (
            f"SignalWithProb({status}, p={self.p_extension:.2f}, "
            f"size={self.size_adjustment:.0%}, runner={self.runner_enabled})"
        )


class ProbabilityGate:
    """Probability-based signal filtering and adjustment.
    
    Example:
        >>> gate = ProbabilityGate(config=ProbabilityGateConfig())
        >>> 
        >>> # Evaluate signal with probability
        >>> result = gate.evaluate(
        ...     signal=candidate_signal,
        ...     p_extension=0.62
        ... )
        >>> 
        >>> if result.passed_gate:
        ...     print(f"Signal passed: size={result.size_adjustment:.0%}, runner={result.runner_enabled}")
        ...     # Execute trade with adjustments
    """
    
    def __init__(
        self,
        config: Optional[ProbabilityGateConfig] = None,
    ) -> None:
        """Initialize probability gate.
        
        Args:
            config: Gating configuration (uses defaults if None)
        """
        self.config = config or ProbabilityGateConfig()
    
    def evaluate(
        self,
        signal: CandidateSignal,
        p_extension: float,
    ) -> SignalWithProbability:
        """Evaluate signal with probability.
        
        Args:
            signal: Candidate signal from playbook
            p_extension: Extension probability (0-1)
            
        Returns:
            SignalWithProbability with gating decision
        """
        # Check hard floor
        if p_extension < self.config.p_min_floor:
            return SignalWithProbability(
                signal=signal,
                p_extension=p_extension,
                passed_gate=False,
                rejection_reason=f"p_extension {p_extension:.2f} < min_floor {self.config.p_min_floor:.2f}",
            )
        
        # Signal passes - determine adjustments
        passed = True
        size_adjustment = 1.0
        runner_enabled = False
        target_adjustment = 1.0
        
        # Check soft floor (reduce size)
        if p_extension < self.config.p_soft_floor:
            size_adjustment = self.config.reduced_size_factor
            logger.debug(
                f"Signal in soft floor zone (p={p_extension:.2f}), "
                f"reducing size to {size_adjustment:.0%}"
            )
        
        # Check runner threshold
        if p_extension >= self.config.p_runner_threshold:
            runner_enabled = True
            logger.debug(f"Runner enabled for p={p_extension:.2f}")
        
        # Adjust targets based on probability
        if self.config.adjust_targets_by_prob:
            if p_extension >= self.config.p_runner_threshold:
                # High probability - increase targets
                target_adjustment = self.config.high_prob_target_mult
            elif p_extension < self.config.p_soft_floor:
                # Low probability - decrease targets
                target_adjustment = self.config.low_prob_target_mult
        
        return SignalWithProbability(
            signal=signal,
            p_extension=p_extension,
            passed_gate=passed,
            size_adjustment=size_adjustment,
            runner_enabled=runner_enabled,
            target_adjustment=target_adjustment,
        )
    
    def batch_evaluate(
        self,
        signals_with_probs: list[tuple[CandidateSignal, float]],
    ) -> list[SignalWithProbability]:
        """Evaluate multiple signals.
        
        Args:
            signals_with_probs: List of (signal, p_extension) tuples
            
        Returns:
            List of SignalWithProbability
        """
        results = []
        
        for signal, p_ext in signals_with_probs:
            result = self.evaluate(signal, p_ext)
            results.append(result)
        
        return results
    
    def filter_passing_signals(
        self,
        results: list[SignalWithProbability],
    ) -> list[SignalWithProbability]:
        """Filter to only passing signals.
        
        Args:
            results: List of SignalWithProbability
            
        Returns:
            List of passing signals
        """
        return [r for r in results if r.passed_gate]


def apply_probability_gate(
    signal: CandidateSignal,
    p_extension: float,
    config: Optional[ProbabilityGateConfig] = None,
) -> SignalWithProbability:
    """Convenience function to apply probability gate.
    
    Args:
        signal: Candidate signal
        p_extension: Extension probability
        config: Optional gate config
        
    Returns:
        SignalWithProbability with gating decision
    """
    gate = ProbabilityGate(config=config)
    return gate.evaluate(signal, p_extension)


def compute_runner_params(
    p_extension: float,
    base_target_r: float = 2.0,
    base_trail_factor: float = 2.0,
    high_prob_multiplier: float = 1.5,
) -> dict:
    """Compute runner parameters based on probability.
    
    Higher probability → more aggressive runner settings.
    
    Args:
        p_extension: Extension probability
        base_target_r: Base runner target
        base_trail_factor: Base trailing ATR multiple
        high_prob_multiplier: Multiplier for high prob
        
    Returns:
        Dictionary with runner parameters
    """
    # Scale target by probability
    # p=0.4 → 0.8x base, p=0.6 → 1.2x base, p=0.8 → 1.5x base
    prob_scale = 0.5 + (p_extension * 2.0)  # Linear scaling
    prob_scale = min(prob_scale, high_prob_multiplier)
    
    runner_target_r = base_target_r * prob_scale
    
    # Trail factor: higher prob → tighter trail (capture more)
    # Inverse relationship: high prob = tighter trail
    trail_factor = base_trail_factor * (1.5 - prob_scale * 0.5)
    trail_factor = max(1.0, trail_factor)  # Min 1.0x ATR
    
    return {
        'runner_target_r': runner_target_r,
        'trail_factor': trail_factor,
        'p_extension': p_extension,
    }


class RunnerActivationManager:
    """Manages runner mode activation and parameters.
    
    Integrates with two-phase stop system to enable runner phase.
    
    Example:
        >>> manager = RunnerActivationManager(
        ...     p_threshold=0.55,
        ...     min_mfe_r=1.5
        ... )
        >>> 
        >>> if manager.should_activate_runner(
        ...     current_mfe_r=1.8,
        ...     p_extension=0.62
        ... ):
        ...     params = manager.get_runner_params(p_extension=0.62)
        ...     # Enable runner with params
    """
    
    def __init__(
        self,
        p_threshold: float = 0.55,
        min_mfe_r: float = 1.5,
        max_mfe_r: float = 3.0,
    ) -> None:
        """Initialize runner activation manager.
        
        Args:
            p_threshold: Min p_extension to enable runner
            min_mfe_r: Min MFE to consider runner
            max_mfe_r: Max MFE to enable runner (too late beyond this)
        """
        self.p_threshold = p_threshold
        self.min_mfe_r = min_mfe_r
        self.max_mfe_r = max_mfe_r
        self.runner_activated = False
    
    def should_activate_runner(
        self,
        current_mfe_r: float,
        p_extension: float,
    ) -> bool:
        """Check if runner should be activated.
        
        Args:
            current_mfe_r: Current MFE in R
            p_extension: Extension probability
            
        Returns:
            True if runner should be activated
        """
        if self.runner_activated:
            return False  # Already activated
        
        # Check probability threshold
        if p_extension < self.p_threshold:
            return False
        
        # Check MFE range
        if current_mfe_r < self.min_mfe_r:
            return False
        
        if current_mfe_r > self.max_mfe_r:
            logger.debug(f"MFE {current_mfe_r:.2f}R too high for runner activation")
            return False
        
        # Activate runner
        self.runner_activated = True
        logger.info(
            f"Runner activated: MFE={current_mfe_r:.2f}R, p={p_extension:.2f}"
        )
        
        return True
    
    def get_runner_params(self, p_extension: float) -> dict:
        """Get runner parameters based on probability.
        
        Args:
            p_extension: Extension probability
            
        Returns:
            Dictionary with runner parameters
        """
        return compute_runner_params(p_extension)

