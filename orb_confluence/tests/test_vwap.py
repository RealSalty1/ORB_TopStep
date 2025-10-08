"""Tests for VWAP calculation."""

import numpy as np
import pytest

from orb_confluence.features.vwap import (
    SessionVWAP,
    calculate_vwap_batch,
)


class TestSessionVWAP:
    """Test SessionVWAP class."""

    def test_insufficient_bars(self):
        """Test that insufficient bars returns NaN."""
        vwap = SessionVWAP(min_bars=3)

        result = vwap.update(100.0, 1000)
        assert result["usable"] == 0.0
        assert np.isnan(result["vwap"])

        result = vwap.update(101.0, 1100)
        assert result["usable"] == 0.0

    def test_sufficient_bars(self):
        """Test that sufficient bars returns valid VWAP."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 1000)
        result = vwap.update(102.0, 1000)

        assert result["usable"] == 1.0
        assert not np.isnan(result["vwap"])

    def test_vwap_calculation(self):
        """Test VWAP calculation accuracy."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 1000)  # PV = 100,000, V = 1000
        result = vwap.update(110.0, 500)  # PV = 55,000, V = 500

        # VWAP = (100,000 + 55,000) / (1000 + 500) = 155,000 / 1500 = 103.333...
        assert result["vwap"] == pytest.approx(103.333, rel=0.01)

    def test_above_vwap_flag(self):
        """Test above_vwap flag."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 1000)
        result = vwap.update(110.0, 1000)  # VWAP = 105

        # Price 110 > VWAP 105
        assert result["above_vwap"] == 1.0
        assert result["below_vwap"] == 0.0

    def test_below_vwap_flag(self):
        """Test below_vwap flag."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 1000)
        vwap.update(102.0, 1000)  # VWAP = 101
        result = vwap.update(100.0, 1000)  # VWAP still ~101

        # Price 100 < VWAP ~101
        assert result["below_vwap"] == 1.0
        assert result["above_vwap"] == 0.0

    def test_reset(self):
        """Test reset functionality."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 1000)
        vwap.update(110.0, 1000)

        # Reset
        vwap.reset()

        # Should be back to insufficient bars
        result = vwap.update(100.0, 1000)
        assert result["usable"] == 0.0

    def test_current_vwap(self):
        """Test current_vwap method."""
        vwap = SessionVWAP(min_bars=2)

        # Before enough bars
        assert vwap.current_vwap() is None

        vwap.update(100.0, 1000)
        vwap.update(110.0, 1000)

        # After enough bars
        current = vwap.current_vwap()
        assert current is not None
        assert current == pytest.approx(105.0, rel=0.01)

    def test_zero_volume(self):
        """Test handling of zero total volume."""
        vwap = SessionVWAP(min_bars=2)

        vwap.update(100.0, 0)
        result = vwap.update(110.0, 0)

        # Zero cumulative volume
        assert result["usable"] == 0.0


class TestCalculateVWAPBatch:
    """Test batch VWAP calculation."""

    def test_batch_calculation(self):
        """Test batch VWAP calculation."""
        prices = np.array([100.0, 102.0, 104.0, 103.0, 105.0])
        volumes = np.array([1000, 1100, 1200, 1000, 1050])

        result = calculate_vwap_batch(prices, volumes, min_bars=2)

        assert result["vwap"].shape == (5,)
        assert result["usable"].shape == (5,)
        assert result["above_vwap"].shape == (5,)
        assert result["below_vwap"].shape == (5,)

        # First bar unusable
        assert result["usable"][0] == 0.0

        # Second bar onwards usable
        assert result["usable"][1] == 1.0

    def test_batch_vwap_values(self):
        """Test batch VWAP value correctness."""
        prices = np.array([100.0, 110.0])
        volumes = np.array([1000, 1000])

        result = calculate_vwap_batch(prices, volumes, min_bars=2)

        # Bar 1: (100*1000 + 110*1000) / (1000 + 1000) = 105
        assert result["vwap"][1] == pytest.approx(105.0, rel=0.01)

    def test_batch_alignment_flags(self):
        """Test batch alignment flags."""
        prices = np.array([100.0, 110.0, 100.0])
        volumes = np.array([1000, 1000, 1000])

        result = calculate_vwap_batch(prices, volumes, min_bars=2)

        # Bar 1: price 110 > vwap 105
        assert result["above_vwap"][1] == 1.0

        # Bar 2: price 100 < vwap ~103.33
        assert result["below_vwap"][2] == 1.0
