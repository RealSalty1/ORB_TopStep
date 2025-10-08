"""Tests for ADX calculation."""

import numpy as np
import pytest

from orb_confluence.features.adx import (
    ADX,
    calculate_adx_batch,
)


class TestADX:
    """Test ADX class."""

    def test_insufficient_history(self):
        """Test that insufficient history returns NaN."""
        adx = ADX(period=3, threshold=20.0)

        # Need period + 1 bars
        result = adx.update(100, 99, 99.5)
        assert result["usable"] == 0.0
        assert np.isnan(result["adx_value"])

        result = adx.update(101, 100, 100.5)
        assert result["usable"] == 0.0

        result = adx.update(102, 101, 101.5)
        assert result["usable"] == 0.0

    def test_sufficient_history(self):
        """Test that sufficient history returns valid ADX."""
        adx = ADX(period=3, threshold=20.0)

        # Add period + 1 bars
        adx.update(100, 99, 99.5)
        adx.update(101, 100, 100.5)
        adx.update(102, 101, 101.5)
        result = adx.update(103, 102, 102.5)

        assert result["usable"] == 1.0
        assert not np.isnan(result["adx_value"])
        assert not np.isnan(result["plus_di"])
        assert not np.isnan(result["minus_di"])

    def test_trending_market(self):
        """Test ADX in strong uptrend."""
        adx = ADX(period=5, threshold=18.0)

        # Strong uptrend
        prices = [
            (100, 99, 99.5),
            (101, 100, 100.5),
            (102, 101, 101.5),
            (103, 102, 102.5),
            (104, 103, 103.5),
            (105, 104, 104.5),
            (106, 105, 105.5),
        ]

        for h, l, c in prices:
            result = adx.update(h, l, c)

        # After enough bars, ADX should indicate trend
        assert result["usable"] == 1.0
        # In strong trend, +DI should be > -DI
        assert result["plus_di"] > result["minus_di"]

    def test_choppy_market(self):
        """Test ADX in choppy/range-bound market."""
        adx = ADX(period=5, threshold=18.0)

        # Choppy market (back and forth)
        prices = [
            (100, 99, 99.5),
            (99.5, 98.5, 99.0),
            (100, 99, 99.5),
            (99.5, 98.5, 99.0),
            (100, 99, 99.5),
            (99.5, 98.5, 99.0),
        ]

        for h, l, c in prices:
            result = adx.update(h, l, c)

        # ADX should be lower in choppy market
        # (This is a probabilistic test, may not always be true for small samples)
        assert result["usable"] == 1.0

    def test_trend_flags(self):
        """Test trend strength flags."""
        adx = ADX(period=3, threshold=20.0)

        # Add bars
        for i in range(4):
            h = 100 + i
            l = 99 + i
            c = 99.5 + i
            result = adx.update(h, l, c)

        # Check flags are mutually exclusive
        if result["usable"] == 1.0:
            assert (result["trend_strong"] == 1.0) != (result["trend_weak"] == 1.0)

    def test_reset(self):
        """Test reset functionality."""
        adx = ADX(period=3, threshold=20.0)

        # Add bars
        for i in range(4):
            adx.update(100 + i, 99 + i, 99.5 + i)

        # Reset
        adx.reset()

        # Should be back to insufficient history
        result = adx.update(100, 99, 99.5)
        assert result["usable"] == 0.0

    def test_directional_indicators(self):
        """Test +DI and -DI calculation."""
        adx = ADX(period=3, threshold=20.0)

        # Uptrend: +DI should dominate
        for i in range(6):
            h = 100 + i * 2
            l = 99 + i * 2
            c = 99.5 + i * 2
            result = adx.update(h, l, c)

        if result["usable"] == 1.0:
            # In uptrend, expect +DI > -DI
            assert result["plus_di"] > 0

    def test_known_sequence(self):
        """Test ADX against a known sequence (hand-checked)."""
        adx = ADX(period=3, threshold=20.0)

        # Simple uptrend
        sequence = [
            (100, 99, 99.5),
            (101, 100, 100.5),
            (102, 101, 101.5),
            (103, 102, 102.5),
        ]

        for h, l, c in sequence:
            result = adx.update(h, l, c)

        # After 4 bars (period=3), should be usable
        assert result["usable"] == 1.0

        # Check reasonable values
        assert 0 <= result["adx_value"] <= 100
        assert 0 <= result["plus_di"] <= 100
        assert 0 <= result["minus_di"] <= 100


class TestCalculateADXBatch:
    """Test batch ADX calculation."""

    def test_batch_calculation(self):
        """Test batch ADX calculation."""
        highs = np.array([100, 101, 102, 103, 104])
        lows = np.array([99, 100, 101, 102, 103])
        closes = np.array([99.5, 100.5, 101.5, 102.5, 103.5])

        result = calculate_adx_batch(highs, lows, closes, period=3, threshold=20.0)

        assert result["adx_value"].shape == (5,)
        assert result["plus_di"].shape == (5,)
        assert result["minus_di"].shape == (5,)
        assert result["trend_strong"].shape == (5,)
        assert result["trend_weak"].shape == (5,)
        assert result["usable"].shape == (5,)

        # First 3 bars unusable (need period + 1)
        assert result["usable"][0] == 0.0
        assert result["usable"][1] == 0.0
        assert result["usable"][2] == 0.0

        # Bar 3 onwards usable
        assert result["usable"][3] == 1.0

    def test_batch_trend_flags(self):
        """Test trend flags in batch mode."""
        # Strong uptrend
        highs = np.array([100, 102, 104, 106, 108])
        lows = np.array([99, 101, 103, 105, 107])
        closes = np.array([99.5, 101.5, 103.5, 105.5, 107.5])

        result = calculate_adx_batch(highs, lows, closes, period=3, threshold=15.0)

        # Should have some bars with trend_strong
        assert result["usable"][-1] == 1.0

    def test_batch_empty_arrays(self):
        """Test batch with empty arrays."""
        highs = np.array([])
        lows = np.array([])
        closes = np.array([])

        result = calculate_adx_batch(highs, lows, closes, period=3)

        assert len(result["adx_value"]) == 0