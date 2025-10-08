"""Tests for relative volume calculation."""

import numpy as np
import pytest

from orb_confluence.features.relative_volume import (
    RelativeVolume,
    calculate_relative_volume_batch,
)


class TestRelativeVolume:
    """Test RelativeVolume class."""

    def test_insufficient_history(self):
        """Test that insufficient history returns NaN."""
        rel_vol = RelativeVolume(lookback=5, min_history=6)

        # First 5 bars
        for i in range(5):
            result = rel_vol.update(1000 + i * 10)
            assert result["usable"] == 0.0
            assert np.isnan(result["rel_vol"])
            assert np.isnan(result["spike_flag"])

    def test_sufficient_history(self):
        """Test that sufficient history returns valid values."""
        rel_vol = RelativeVolume(lookback=5, min_history=6)

        # Add 6 bars
        volumes = [1000, 1100, 1000, 1050, 1000, 1025]
        for v in volumes:
            result = rel_vol.update(v)

        # Last result should be usable
        assert result["usable"] == 1.0
        assert not np.isnan(result["rel_vol"])

    def test_spike_detection(self):
        """Test spike detection logic."""
        rel_vol = RelativeVolume(lookback=5, spike_mult=2.0, min_history=5)

        # Add normal volumes
        for v in [1000, 1000, 1000, 1000, 1000]:
            result = rel_vol.update(v)

        assert result["spike_flag"] == 0.0  # No spike

        # Add spike (3x average)
        result = rel_vol.update(3000)
        assert result["spike_flag"] == 1.0  # Spike detected
        assert result["rel_vol"] >= 2.0

    def test_no_spike_normal_volume(self):
        """Test no spike flag for normal volume."""
        rel_vol = RelativeVolume(lookback=5, spike_mult=1.5, min_history=5)

        # Add consistent volumes
        for v in [1000, 1100, 1000, 1050, 1025]:
            result = rel_vol.update(v)

        # Add slightly above average
        result = rel_vol.update(1100)
        # 1100 / avg(1000, 1100, 1000, 1050, 1025) = 1100 / 1035 = 1.06 < 1.5
        assert result["spike_flag"] == 0.0

    def test_relative_volume_calculation(self):
        """Test relative volume calculation accuracy."""
        rel_vol = RelativeVolume(lookback=3, min_history=3)

        # Known volumes
        rel_vol.update(1000)  # Avg: 0 → use 1000
        rel_vol.update(1000)  # Avg: 1000
        result = rel_vol.update(2000)  # Avg: 1000

        # rel_vol = 2000 / avg(1000, 1000) = 2000 / 1000 = 2.0
        assert result["rel_vol"] == pytest.approx(2.0, rel=0.01)

    def test_reset(self):
        """Test reset functionality."""
        rel_vol = RelativeVolume(lookback=5, min_history=5)

        # Add bars
        for v in [1000, 1100, 1000, 1050, 1025]:
            rel_vol.update(v)

        # Reset
        rel_vol.reset()

        # Should be back to insufficient history
        result = rel_vol.update(1000)
        assert result["usable"] == 0.0

    def test_zero_average_volume(self):
        """Test handling of zero average volume."""
        rel_vol = RelativeVolume(lookback=3, min_history=3)

        # Add zero volumes
        for v in [0, 0, 0]:
            result = rel_vol.update(v)

        # Should return unusable
        assert result["usable"] == 0.0
        assert np.isnan(result["rel_vol"])


class TestCalculateRelativeVolumeBatch:
    """Test batch relative volume calculation."""

    def test_batch_calculation(self):
        """Test batch relative volume calculation."""
        volumes = np.array([1000, 1000, 1000, 2000, 1500])

        result = calculate_relative_volume_batch(volumes, lookback=3, spike_mult=1.5)

        assert result["rel_vol"].shape == (5,)
        assert result["spike_flag"].shape == (5,)
        assert result["usable"].shape == (5,)

        # First 2 bars should be unusable (need lookback bars)
        assert result["usable"][0] == 0.0
        assert result["usable"][1] == 0.0

        # Bar 3 onwards should be usable
        assert result["usable"][3] == 1.0

    def test_batch_spike_detection(self):
        """Test spike detection in batch mode."""
        volumes = np.array([1000, 1000, 1000, 3000])  # Last is spike

        result = calculate_relative_volume_batch(volumes, lookback=3, spike_mult=2.0)

        # Last bar: 3000 / avg(1000, 1000, 1000) = 3.0 > 2.0
        assert result["spike_flag"][-1] == 1.0

    def test_batch_empty_array(self):
        """Test batch with empty array."""
        volumes = np.array([])

        result = calculate_relative_volume_batch(volumes, lookback=3)

        assert len(result["rel_vol"]) == 0