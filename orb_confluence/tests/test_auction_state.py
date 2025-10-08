"""Tests for auction state classification."""

from datetime import datetime

import pytest

from orb_confluence.features.auction_metrics import AuctionMetrics, GapType
from orb_confluence.features.or_layers import DualORState
from orb_confluence.states.auction_state import (
    AuctionState,
    AuctionStateClassifier,
    classify_auction_state,
)


@pytest.fixture
def initiative_metrics():
    """Create metrics showing INITIATIVE state."""
    return AuctionMetrics(
        drive_energy=0.75,  # High
        rotations=1,  # Low
        volume_z=1.5,  # High
        volume_ratio=1.3,
        gap_type=GapType.NO_GAP,
        gap_size_norm=0.0,
        open_vs_prior_mid=0.2,
        overnight_range_pct=0.3,
        overnight_inventory_bias=0.1,
        bar_count=15,
        avg_body_pct=0.7,
        max_wick_ratio=0.3,
        start_ts=datetime(2024, 1, 2, 14, 30),
        end_ts=datetime(2024, 1, 2, 14, 45),
    )


@pytest.fixture
def compression_metrics():
    """Create metrics showing COMPRESSION state."""
    return AuctionMetrics(
        drive_energy=0.15,  # Low
        rotations=2,
        volume_z=-0.5,  # Below average
        volume_ratio=0.8,
        gap_type=GapType.INSIDE,
        gap_size_norm=0.0,
        open_vs_prior_mid=0.0,
        overnight_range_pct=0.2,
        overnight_inventory_bias=0.0,
        bar_count=15,
        avg_body_pct=0.3,  # Small bodies
        max_wick_ratio=0.8,
        start_ts=datetime(2024, 1, 2, 14, 30),
        end_ts=datetime(2024, 1, 2, 14, 45),
    )


@pytest.fixture
def balanced_metrics():
    """Create metrics showing BALANCED state."""
    return AuctionMetrics(
        drive_energy=0.45,  # Moderate
        rotations=5,  # High
        volume_z=0.2,
        volume_ratio=1.1,
        gap_type=GapType.INSIDE,
        gap_size_norm=0.0,
        open_vs_prior_mid=0.1,
        overnight_range_pct=0.3,
        overnight_inventory_bias=0.2,
        bar_count=15,
        avg_body_pct=0.5,
        max_wick_ratio=0.5,
        start_ts=datetime(2024, 1, 2, 14, 30),
        end_ts=datetime(2024, 1, 2, 14, 45),
    )


@pytest.fixture
def gap_rev_metrics():
    """Create metrics showing GAP_REV state."""
    return AuctionMetrics(
        drive_energy=0.25,  # Low (not extending)
        rotations=2,
        volume_z=0.5,
        volume_ratio=1.1,
        gap_type=GapType.FULL_UP,  # Gap up
        gap_size_norm=0.8,  # Significant gap
        open_vs_prior_mid=1.5,
        overnight_range_pct=0.4,
        overnight_inventory_bias=0.3,
        bar_count=15,
        avg_body_pct=0.4,
        max_wick_ratio=1.5,  # High wicks (rejection)
        start_ts=datetime(2024, 1, 2, 14, 30),
        end_ts=datetime(2024, 1, 2, 14, 45),
    )


@pytest.fixture
def narrow_or():
    """Create narrow OR state (compression)."""
    return DualORState(
        micro_start_ts=datetime(2024, 1, 2, 14, 30),
        micro_end_ts=datetime(2024, 1, 2, 14, 35),
        micro_high=5001.0,
        micro_low=5000.0,
        micro_width=1.0,
        micro_finalized=True,
        primary_start_ts=datetime(2024, 1, 2, 14, 30),
        primary_end_ts=datetime(2024, 1, 2, 14, 45),
        primary_high=5002.0,
        primary_low=4999.0,
        primary_width=3.0,
        primary_finalized=True,
        primary_duration_used=15,
        micro_width_norm=0.4,  # Narrow
        primary_width_norm=0.3,  # Very narrow
    )


@pytest.fixture
def wide_or():
    """Create wide OR state (expansion)."""
    return DualORState(
        micro_start_ts=datetime(2024, 1, 2, 14, 30),
        micro_end_ts=datetime(2024, 1, 2, 14, 35),
        micro_high=5003.0,
        micro_low=4997.0,
        micro_width=6.0,
        micro_finalized=True,
        primary_start_ts=datetime(2024, 1, 2, 14, 30),
        primary_end_ts=datetime(2024, 1, 2, 14, 45),
        primary_high=5010.0,
        primary_low=4990.0,
        primary_width=20.0,
        primary_finalized=True,
        primary_duration_used=15,
        micro_width_norm=2.4,
        primary_width_norm=2.0,
    )


def test_classifier_initialization():
    """Test classifier initialization with default parameters."""
    classifier = AuctionStateClassifier()
    
    assert classifier.drive_threshold == 0.55
    assert classifier.rotations_max == 2
    assert classifier.vol_z_threshold == 1.0


def test_classify_initiative(initiative_metrics, wide_or):
    """Test INITIATIVE classification."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(initiative_metrics, wide_or)
    
    assert result.state == AuctionState.INITIATIVE
    assert result.confidence > 0.5
    assert "drive" in result.reason.lower()


def test_classify_compression(compression_metrics, narrow_or):
    """Test COMPRESSION classification."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(compression_metrics, narrow_or)
    
    assert result.state == AuctionState.COMPRESSION
    assert result.confidence > 0.5
    assert "narrow" in result.reason.lower() or "width" in result.reason.lower()


def test_classify_balanced(balanced_metrics, wide_or):
    """Test BALANCED classification."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(balanced_metrics, wide_or)
    
    assert result.state == AuctionState.BALANCED
    assert result.confidence > 0.3
    assert "rotation" in result.reason.lower()


def test_classify_gap_reversion(gap_rev_metrics, wide_or):
    """Test GAP_REV classification."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(gap_rev_metrics, wide_or)
    
    assert result.state == AuctionState.GAP_REV
    assert result.confidence > 0.5
    assert "gap" in result.reason.lower()


def test_state_scores_all_present(initiative_metrics, wide_or):
    """Test that all states get scored."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(initiative_metrics, wide_or)
    
    # All states should be in scores
    expected_states = [
        AuctionState.INITIATIVE,
        AuctionState.BALANCED,
        AuctionState.COMPRESSION,
        AuctionState.GAP_REV,
        AuctionState.INVENTORY_FIX,
    ]
    
    for state in expected_states:
        assert state in result.state_scores
        assert 0.0 <= result.state_scores[state] <= 1.0


def test_convenience_function(initiative_metrics, wide_or):
    """Test convenience classify_auction_state function."""
    result = classify_auction_state(initiative_metrics, wide_or)
    
    assert isinstance(result.state, AuctionState)
    assert 0.0 <= result.confidence <= 1.0


def test_custom_thresholds():
    """Test classifier with custom thresholds."""
    classifier = AuctionStateClassifier(
        drive_energy_threshold=0.7,  # Higher threshold
        rotations_initiative_max=1,  # Stricter
    )
    
    # Metrics that would pass default but fail custom
    metrics = AuctionMetrics(
        drive_energy=0.6,  # Below custom threshold
        rotations=2,  # Above custom max
        volume_z=1.0,
        volume_ratio=1.0,
        gap_type=GapType.NO_GAP,
        gap_size_norm=0.0,
        open_vs_prior_mid=0.0,
        overnight_range_pct=0.0,
        overnight_inventory_bias=0.0,
        bar_count=15,
        avg_body_pct=0.5,
        max_wick_ratio=0.5,
        start_ts=datetime(2024, 1, 2, 14, 30),
        end_ts=datetime(2024, 1, 2, 14, 45),
    )
    
    wide_or = DualORState(
        micro_start_ts=datetime(2024, 1, 2, 14, 30),
        micro_end_ts=datetime(2024, 1, 2, 14, 35),
        micro_high=5005.0,
        micro_low=4995.0,
        micro_width=10.0,
        micro_finalized=True,
        primary_start_ts=datetime(2024, 1, 2, 14, 30),
        primary_end_ts=datetime(2024, 1, 2, 14, 45),
        primary_high=5010.0,
        primary_low=4990.0,
        primary_width=20.0,
        primary_finalized=True,
        primary_duration_used=15,
        micro_width_norm=4.0,
        primary_width_norm=8.0,
    )
    
    result = classifier.classify(metrics, wide_or)
    
    # Should not be classified as INITIATIVE with strict thresholds
    assert result.state != AuctionState.INITIATIVE


def test_confidence_bounds(initiative_metrics, wide_or):
    """Test confidence is always between 0 and 1."""
    classifier = AuctionStateClassifier()
    
    result = classifier.classify(initiative_metrics, wide_or)
    
    assert 0.0 <= result.confidence <= 1.0

