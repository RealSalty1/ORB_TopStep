"""Tests for auction metrics calculation."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.features.auction_metrics import (
    AuctionMetricsBuilder,
    GapType,
    compute_auction_metrics_from_bars,
)


@pytest.fixture
def initiative_bars():
    """Create bars showing initiative (strong directional drive)."""
    start = datetime(2024, 1, 2, 14, 30)
    bars = []
    
    for i in range(15):
        # Strong bullish bars
        bar = pd.Series({
            "timestamp_utc": start + timedelta(minutes=i),
            "open": 5000.0 + i * 1.0,
            "high": 5002.0 + i * 1.0,
            "low": 4999.5 + i * 1.0,
            "close": 5001.5 + i * 1.0,
            "volume": 1200,
        })
        bars.append(bar)
    
    return bars


@pytest.fixture
def compression_bars():
    """Create bars showing compression (narrow, low energy)."""
    start = datetime(2024, 1, 2, 14, 30)
    bars = []
    
    for i in range(15):
        # Narrow range bars
        bar = pd.Series({
            "timestamp_utc": start + timedelta(minutes=i),
            "open": 5000.0,
            "high": 5000.5,
            "low": 4999.5,
            "close": 5000.0 + (0.1 if i % 2 == 0 else -0.1),
            "volume": 800,
        })
        bars.append(bar)
    
    return bars


def test_auction_metrics_builder_initialization():
    """Test AuctionMetricsBuilder initialization."""
    start = datetime(2024, 1, 2, 14, 30)
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
        prior_high=5010.0,
        prior_low=4990.0,
        prior_close=5000.0,
    )
    
    assert builder.start_ts == start
    assert builder.atr_14 == 2.5
    assert len(builder.bars) == 0


def test_drive_energy_calculation(initiative_bars):
    """Test drive energy calculation for initiative."""
    start = initiative_bars[0]["timestamp_utc"]
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
    )
    
    for bar in initiative_bars:
        builder.add_bar(bar)
    
    metrics = builder.compute()
    
    # Should have high drive energy (strong directional)
    assert metrics.drive_energy > 0.5
    
    # Should have low rotations (no direction changes)
    assert metrics.rotations <= 2


def test_rotations_count():
    """Test rotation counting."""
    start = datetime(2024, 1, 2, 14, 30)
    
    # Create alternating direction bars
    bars = []
    for i in range(10):
        if i % 2 == 0:
            # Bullish
            bar = pd.Series({
                "timestamp_utc": start + timedelta(minutes=i),
                "open": 5000.0,
                "high": 5002.0,
                "low": 4999.0,
                "close": 5001.5,
                "volume": 1000,
            })
        else:
            # Bearish
            bar = pd.Series({
                "timestamp_utc": start + timedelta(minutes=i),
                "open": 5001.5,
                "high": 5002.0,
                "low": 4999.0,
                "close": 4999.5,
                "volume": 1000,
            })
        bars.append(bar)
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
    )
    
    for bar in bars:
        builder.add_bar(bar)
    
    metrics = builder.compute()
    
    # Should have multiple rotations (alternating)
    assert metrics.rotations >= 5


def test_gap_classification_full_up():
    """Test gap classification - full gap up."""
    start = datetime(2024, 1, 2, 14, 30)
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
        prior_high=5000.0,
        prior_low=4990.0,
        prior_close=4995.0,
    )
    
    # Add bar opening above prior high
    bar = pd.Series({
        "timestamp_utc": start,
        "open": 5005.0,  # Above prior high
        "high": 5010.0,
        "low": 5004.0,
        "close": 5008.0,
        "volume": 1000,
    })
    builder.add_bar(bar)
    
    metrics = builder.compute()
    
    assert metrics.gap_type == GapType.FULL_UP
    assert metrics.gap_size_norm > 0  # Should be normalized by ATR


def test_gap_classification_inside():
    """Test gap classification - inside prior range."""
    start = datetime(2024, 1, 2, 14, 30)
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
        prior_high=5000.0,
        prior_low=4990.0,
        prior_close=4995.0,
    )
    
    # Add bar opening inside prior range
    bar = pd.Series({
        "timestamp_utc": start,
        "open": 4995.0,  # Inside prior range
        "high": 4998.0,
        "low": 4992.0,
        "close": 4996.0,
        "volume": 1000,
    })
    builder.add_bar(bar)
    
    metrics = builder.compute()
    
    assert metrics.gap_type in [GapType.INSIDE, GapType.PARTIAL_UP, GapType.PARTIAL_DOWN]


def test_volume_metrics():
    """Test volume Z-score calculation."""
    start = datetime(2024, 1, 2, 14, 30)
    
    builder = AuctionMetricsBuilder(
        start_ts=start,
        atr_14=2.5,
        adr_20=50.0,
    )
    
    # Add bars with known volume
    for i in range(10):
        bar = pd.Series({
            "timestamp_utc": start + timedelta(minutes=i),
            "open": 5000.0,
            "high": 5001.0,
            "low": 4999.0,
            "close": 5000.5,
            "volume": 1500,  # 50% above expected
        })
        builder.add_bar(bar, expected_volume=1000)
    
    metrics = builder.compute()
    
    # Volume ratio should be 1.5
    assert metrics.volume_ratio == pytest.approx(1.5, abs=0.01)
    
    # Z-score should be positive (above expected)
    assert metrics.volume_z > 0


def test_batch_computation():
    """Test batch computation from DataFrame."""
    start = datetime(2024, 1, 2, 14, 30)
    
    bars = []
    for i in range(15):
        bars.append({
            "timestamp_utc": start + timedelta(minutes=i),
            "open": 5000.0 + i * 0.5,
            "high": 5002.0 + i * 0.5,
            "low": 4999.0 + i * 0.5,
            "close": 5001.0 + i * 0.5,
            "volume": 1000,
        })
    
    df = pd.DataFrame(bars)
    
    metrics = compute_auction_metrics_from_bars(
        df=df,
        or_start=start,
        or_end=start + timedelta(minutes=15),
        atr_14=2.5,
        adr_20=50.0,
        prior_high=5010.0,
        prior_low=4990.0,
        prior_close=5000.0,
    )
    
    assert metrics.bar_count == 15
    assert metrics.drive_energy >= 0
    assert metrics.rotations >= 0

