"""Tests for confluence scoring engine."""

import pytest

from orb_confluence.strategy.scoring import (
    compute_score,
    analyze_confluence,
    validate_factor_weights,
    get_factor_contribution,
)


class TestComputeScore:
    """Test compute_score function."""

    def test_basic_score_calculation(self):
        """Test basic score calculation with equal weights."""
        factor_flags = {
            'price_action': 1.0,
            'rel_vol': 1.0,
            'profile': 0.0,
            'vwap': 1.0,
            'adx': 1.0,
        }
        weights = {k: 1.0 for k in factor_flags}

        score, required, passed = compute_score(
            direction='long',
            factor_flags=factor_flags,
            weights=weights,
            trend_weak=False,
            base_required=2,
            weak_trend_required=3,
        )

        assert score == 4.0  # 4 factors active
        assert required == 2.0  # Base requirement (strong trend)
        assert passed is True

    def test_weak_trend_higher_requirement(self):
        """Test that weak trend requires higher score."""
        factor_flags = {
            'price_action': 1.0,
            'rel_vol': 1.0,
            'profile': 0.0,
            'vwap': 0.0,
            'adx': 0.0,
        }
        weights = {k: 1.0 for k in factor_flags}

        # Strong trend (score=2, required=2, pass)
        score, required, passed = compute_score(
            'long', factor_flags, weights, trend_weak=False, base_required=2, weak_trend_required=3
        )
        assert score == 2.0
        assert required == 2.0
        assert passed is True

        # Weak trend (score=2, required=3, fail)
        score, required, passed = compute_score(
            'long', factor_flags, weights, trend_weak=True, base_required=2, weak_trend_required=3
        )
        assert score == 2.0
        assert required == 3.0
        assert passed is False

    def test_weighted_scoring(self):
        """Test weighted scoring."""
        factor_flags = {
            'price_action': 1.0,
            'rel_vol': 1.0,
            'profile': 1.0,
        }
        weights = {
            'price_action': 2.0,  # Double weight
            'rel_vol': 1.0,
            'profile': 0.5,  # Half weight
        }

        score, required, passed = compute_score(
            'long', factor_flags, weights, trend_weak=False, base_required=2
        )

        # Score = 1.0*2.0 + 1.0*1.0 + 1.0*0.5 = 3.5
        assert score == 3.5
        assert passed is True

    def test_no_factors_pass(self):
        """Test with no factors passing."""
        factor_flags = {k: 0.0 for k in ['price_action', 'rel_vol', 'profile', 'vwap', 'adx']}
        weights = {k: 1.0 for k in factor_flags}

        score, required, passed = compute_score(
            'long', factor_flags, weights, trend_weak=False, base_required=1
        )

        assert score == 0.0
        assert passed is False

    def test_invalid_direction(self):
        """Test that invalid direction raises error."""
        factor_flags = {'price_action': 1.0}
        weights = {'price_action': 1.0}

        with pytest.raises(ValueError, match="Invalid direction"):
            compute_score('up', factor_flags, weights)

    def test_short_direction(self):
        """Test short direction scoring."""
        factor_flags = {'price_action': 1.0, 'rel_vol': 1.0}
        weights = {k: 1.0 for k in factor_flags}

        score, required, passed = compute_score(
            'short', factor_flags, weights, trend_weak=False, base_required=1
        )

        assert score == 2.0
        assert passed is True


class TestAnalyzeConfluence:
    """Test analyze_confluence function."""

    def test_long_only_pass(self):
        """Test when only long passes."""
        long_flags = {'price_action': 1.0, 'rel_vol': 1.0, 'profile': 1.0}
        short_flags = {'price_action': 0.0, 'rel_vol': 0.0, 'profile': 0.0}
        weights = {k: 1.0 for k in long_flags}

        result = analyze_confluence(
            long_flags, short_flags, weights, trend_weak=False, base_required=2
        )

        assert result['long_pass'] is True
        assert result['short_pass'] is False
        assert result['direction'] == 'long'
        assert result['long_score'] == 3.0
        assert result['short_score'] == 0.0

    def test_short_only_pass(self):
        """Test when only short passes."""
        long_flags = {'price_action': 0.0, 'rel_vol': 1.0}
        short_flags = {'price_action': 1.0, 'rel_vol': 1.0}
        weights = {k: 1.0 for k in long_flags}

        result = analyze_confluence(
            long_flags, short_flags, weights, trend_weak=False, base_required=2
        )

        assert result['long_pass'] is False
        assert result['short_pass'] is True
        assert result['direction'] == 'short'

    def test_both_pass_long_priority(self):
        """Test when both pass, long takes priority if scores equal."""
        long_flags = {'price_action': 1.0, 'rel_vol': 1.0}
        short_flags = {'price_action': 1.0, 'rel_vol': 1.0}
        weights = {k: 1.0 for k in long_flags}

        result = analyze_confluence(
            long_flags, short_flags, weights, trend_weak=False, base_required=1
        )

        assert result['long_pass'] is True
        assert result['short_pass'] is True
        assert result['direction'] == 'long'  # Long priority when tied

    def test_both_pass_higher_score_wins(self):
        """Test when both pass, higher score wins."""
        long_flags = {'price_action': 1.0, 'rel_vol': 1.0}
        short_flags = {'price_action': 1.0, 'rel_vol': 1.0, 'profile': 1.0}
        weights = {k: 1.0 for k in ['price_action', 'rel_vol', 'profile']}

        result = analyze_confluence(
            long_flags, short_flags, weights, trend_weak=False, base_required=1
        )

        assert result['long_pass'] is True
        assert result['short_pass'] is True
        assert result['short_score'] > result['long_score']
        assert result['direction'] == 'short'

    def test_neither_pass(self):
        """Test when neither passes."""
        long_flags = {'price_action': 1.0}
        short_flags = {'price_action': 0.0}
        weights = {'price_action': 1.0}

        result = analyze_confluence(
            long_flags, short_flags, weights, trend_weak=False, base_required=5
        )

        assert result['long_pass'] is False
        assert result['short_pass'] is False
        assert result['direction'] is None


class TestValidateFactorWeights:
    """Test validate_factor_weights function."""

    def test_valid_weights(self):
        """Test that valid weights pass."""
        weights = {'price_action': 1.0, 'rel_vol': 1.5, 'profile': 0.0}
        assert validate_factor_weights(weights) is True

    def test_negative_weight_raises_error(self):
        """Test that negative weight raises error."""
        weights = {'price_action': 1.0, 'rel_vol': -0.5}

        with pytest.raises(ValueError, match="must be non-negative"):
            validate_factor_weights(weights)


class TestGetFactorContribution:
    """Test get_factor_contribution function."""

    def test_factor_contributions(self):
        """Test individual factor contributions."""
        flags = {
            'price_action': 1.0,
            'rel_vol': 1.0,
            'profile': 0.0,
            'vwap': 1.0,
        }
        weights = {
            'price_action': 2.0,
            'rel_vol': 1.0,
            'profile': 1.0,
            'vwap': 1.5,
        }

        contrib = get_factor_contribution(flags, weights)

        assert contrib['price_action'] == 2.0  # 1.0 * 2.0
        assert contrib['rel_vol'] == 1.0  # 1.0 * 1.0
        assert contrib['profile'] == 0.0  # 0.0 * 1.0
        assert contrib['vwap'] == 1.5  # 1.0 * 1.5

    def test_contributions_sum_to_score(self):
        """Test that contributions sum to total score."""
        flags = {'a': 1.0, 'b': 1.0, 'c': 0.5}
        weights = {'a': 2.0, 'b': 1.0, 'c': 1.0}

        contrib = get_factor_contribution(flags, weights)
        total = sum(contrib.values())

        # Should match compute_score result
        score, _, _ = compute_score('long', flags, weights)
        assert total == score