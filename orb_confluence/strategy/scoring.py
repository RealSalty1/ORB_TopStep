"""Confluence scoring engine for multi-factor validation.

Aggregates factor signals with optional weighting and applies
threshold-based gating for trade entry.
"""

from typing import Dict, Tuple

from loguru import logger


def compute_score(
    direction: str,
    factor_flags: Dict[str, float],
    weights: Dict[str, float],
    trend_weak: bool = False,
    base_required: int = 2,
    weak_trend_required: int = 3,
) -> Tuple[float, float, bool]:
    """Compute confluence score with optional weighting.

    Args:
        direction: Trade direction ('long' or 'short').
        factor_flags: Dictionary of factor flags (1.0 = active, 0.0 = inactive).
            Expected keys: 'price_action', 'rel_vol', 'profile', 'vwap', 'adx'
        weights: Dictionary of factor weights (default 1.0 for equal weighting).
        trend_weak: Whether trend is weak (ADX < threshold).
        base_required: Base score required for entry (strong trend).
        weak_trend_required: Score required in weak trend conditions.

    Returns:
        Tuple of (score, required_score, pass_bool).

    Examples:
        >>> factor_flags = {
        ...     'price_action': 1.0,
        ...     'rel_vol': 1.0,
        ...     'profile': 0.0,
        ...     'vwap': 1.0,
        ...     'adx': 1.0
        ... }
        >>> weights = {'price_action': 1.0, 'rel_vol': 1.0, 'profile': 1.0, 'vwap': 1.0, 'adx': 1.0}
        >>> score, required, passed = compute_score('long', factor_flags, weights, False, 2, 3)
        >>> assert score == 4.0
        >>> assert passed is True

    Notes:
        - Score is sum of (flag × weight) for each factor
        - Required score depends on trend strength
        - Pass if score >= required_score
    """
    if direction not in ['long', 'short']:
        raise ValueError(f"Invalid direction: {direction}. Must be 'long' or 'short'")

    # Calculate weighted score
    score = 0.0
    for factor_name, flag_value in factor_flags.items():
        weight = weights.get(factor_name, 1.0)
        score += flag_value * weight

    # Determine required score based on trend strength
    required_score = weak_trend_required if trend_weak else base_required

    # Check if score meets requirement
    passed = score >= required_score

    logger.debug(
        f"{direction.upper()} confluence: score={score:.1f}, required={required_score:.1f}, "
        f"trend_weak={trend_weak}, passed={passed}"
    )

    return score, float(required_score), passed


def analyze_confluence(
    factor_flags_long: Dict[str, float],
    factor_flags_short: Dict[str, float],
    weights: Dict[str, float],
    trend_weak: bool = False,
    base_required: int = 2,
    weak_trend_required: int = 3,
) -> Dict[str, any]:
    """Analyze confluence for both long and short directions.

    Args:
        factor_flags_long: Long direction factor flags.
        factor_flags_short: Short direction factor flags.
        weights: Factor weights.
        trend_weak: Whether trend is weak.
        base_required: Base score requirement.
        weak_trend_required: Weak trend score requirement.

    Returns:
        Dictionary with:
        - long_score: Long confluence score
        - long_required: Long required score
        - long_pass: Long pass boolean
        - short_score: Short confluence score
        - short_required: Short required score
        - short_pass: Short pass boolean
        - direction: 'long', 'short', or None if neither passes

    Examples:
        >>> long_flags = {'price_action': 1.0, 'rel_vol': 1.0, 'profile': 1.0, 'vwap': 0.0, 'adx': 1.0}
        >>> short_flags = {'price_action': 0.0, 'rel_vol': 0.0, 'profile': 0.0, 'vwap': 0.0, 'adx': 0.0}
        >>> weights = {k: 1.0 for k in long_flags}
        >>> result = analyze_confluence(long_flags, short_flags, weights, False, 3, 4)
        >>> assert result['long_pass'] is True
        >>> assert result['short_pass'] is False
        >>> assert result['direction'] == 'long'
    """
    # Compute long score
    long_score, long_required, long_pass = compute_score(
        direction='long',
        factor_flags=factor_flags_long,
        weights=weights,
        trend_weak=trend_weak,
        base_required=base_required,
        weak_trend_required=weak_trend_required,
    )

    # Compute short score
    short_score, short_required, short_pass = compute_score(
        direction='short',
        factor_flags=factor_flags_short,
        weights=weights,
        trend_weak=trend_weak,
        base_required=base_required,
        weak_trend_required=weak_trend_required,
    )

    # Determine direction (prioritize long if both pass)
    direction = None
    if long_pass and not short_pass:
        direction = 'long'
    elif short_pass and not long_pass:
        direction = 'short'
    elif long_pass and short_pass:
        # Both pass: choose higher score, or long if tied
        direction = 'long' if long_score >= short_score else 'short'

    return {
        'long_score': long_score,
        'long_required': long_required,
        'long_pass': long_pass,
        'short_score': short_score,
        'short_required': short_required,
        'short_pass': short_pass,
        'direction': direction,
    }


def validate_factor_weights(weights: Dict[str, float]) -> bool:
    """Validate that factor weights are non-negative.

    Args:
        weights: Dictionary of factor weights.

    Returns:
        True if all weights are non-negative.

    Raises:
        ValueError: If any weight is negative.
    """
    for factor_name, weight in weights.items():
        if weight < 0:
            raise ValueError(f"Weight for {factor_name} must be non-negative, got {weight}")
    return True


def get_factor_contribution(
    factor_flags: Dict[str, float],
    weights: Dict[str, float],
) -> Dict[str, float]:
    """Calculate individual factor contributions to total score.

    Args:
        factor_flags: Factor flags.
        weights: Factor weights.

    Returns:
        Dictionary of factor names to their contribution (flag × weight).

    Examples:
        >>> flags = {'price_action': 1.0, 'rel_vol': 1.0, 'profile': 0.0}
        >>> weights = {'price_action': 1.5, 'rel_vol': 1.0, 'profile': 1.0}
        >>> contrib = get_factor_contribution(flags, weights)
        >>> assert contrib['price_action'] == 1.5
        >>> assert contrib['rel_vol'] == 1.0
        >>> assert contrib['profile'] == 0.0
    """
    contributions = {}
    for factor_name, flag_value in factor_flags.items():
        weight = weights.get(factor_name, 1.0)
        contributions[factor_name] = flag_value * weight
    return contributions