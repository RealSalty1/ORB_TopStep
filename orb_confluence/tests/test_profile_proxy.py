"""Tests for profile proxy factor."""

import numpy as np
import pytest

from orb_confluence.features.profile_proxy import (
    ProfileProxy,
    calculate_profile_proxy,
)


class TestProfileProxy:
    """Test ProfileProxy class."""

    def test_initialization(self):
        """Test ProfileProxy initialization."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        assert proxy.val_pct == 0.25
        assert proxy.vah_pct == 0.75

    def test_invalid_initialization(self):
        """Test that invalid percentiles raise error."""
        with pytest.raises(ValueError):
            ProfileProxy(val_pct=0.75, vah_pct=0.25)  # val > vah

        with pytest.raises(ValueError):
            ProfileProxy(val_pct=0.5, vah_pct=0.5)  # val == vah

    def test_val_vah_calculation(self):
        """Test VAL/VAH calculation."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=105.0,
            or_high=104.0,
            or_low=103.0,
            or_finalized=True,
        )

        # Range = 10, VAL = 100 + 10*0.25 = 102.5, VAH = 100 + 10*0.75 = 107.5
        assert result["val"] == 102.5
        assert result["vah"] == 107.5
        assert result["mid"] == 105.0

    def test_bullish_alignment_above_vah(self):
        """Test bullish alignment when price above VAH."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Prior day range: 100-110, VAH = 107.5
        # Current close = 108 (above VAH)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=108.0,
            or_high=107.0,
            or_low=106.0,
            or_finalized=True,
        )

        assert result["profile_long_flag"] == 1.0
        assert result["profile_short_flag"] == 0.0

    def test_bearish_alignment_below_val(self):
        """Test bearish alignment when price below VAL."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Prior day range: 100-110, VAL = 102.5
        # Current close = 101 (below VAL)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=101.0,
            or_high=103.0,
            or_low=102.0,
            or_finalized=True,
        )

        assert result["profile_long_flag"] == 0.0
        assert result["profile_short_flag"] == 1.0

    def test_bullish_in_value_area_or_above_mid(self):
        """Test bullish when in value area but OR above midpoint."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Prior day: 100-110, VAL=102.5, VAH=107.5, Mid=105.0
        # Current close = 104 (in value area)
        # OR = 106-107 (OR low > mid)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=104.0,
            or_high=107.0,
            or_low=106.0,
            or_finalized=True,
        )

        assert result["profile_long_flag"] == 1.0

    def test_bearish_in_value_area_or_below_mid(self):
        """Test bearish when in value area but OR below midpoint."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Prior day: 100-110, VAL=102.5, VAH=107.5, Mid=105.0
        # Current close = 106 (in value area)
        # OR = 103-104 (OR high < mid)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=106.0,
            or_high=104.0,
            or_low=103.0,
            or_finalized=True,
        )

        assert result["profile_short_flag"] == 1.0

    def test_or_not_finalized(self):
        """Test that unfinalized OR returns zeros."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=105.0,
            or_high=104.0,
            or_low=103.0,
            or_finalized=False,  # Not finalized
        )

        assert np.isnan(result["val"])
        assert np.isnan(result["vah"])
        assert result["profile_long_flag"] == 0.0
        assert result["profile_short_flag"] == 0.0

    def test_boundary_at_vah(self):
        """Test boundary condition at VAH."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Price exactly at VAH (should not trigger long)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=107.5,  # Exactly at VAH
            or_high=107.0,
            or_low=106.0,
            or_finalized=True,
        )

        # At VAH, not above
        assert result["profile_long_flag"] == 0.0

    def test_boundary_at_val(self):
        """Test boundary condition at VAL."""
        proxy = ProfileProxy(val_pct=0.25, vah_pct=0.75)

        # Price exactly at VAL (should not trigger short)
        result = proxy.analyze(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=102.5,  # Exactly at VAL
            or_high=104.0,
            or_low=103.0,
            or_finalized=True,
        )

        # At VAL, not below
        assert result["profile_short_flag"] == 0.0


class TestCalculateProfileProxy:
    """Test convenience function."""

    def test_calculate_profile_proxy(self):
        """Test profile proxy calculation convenience function."""
        result = calculate_profile_proxy(
            prior_day_high=110.0,
            prior_day_low=100.0,
            current_close=108.0,
            or_high=107.0,
            or_low=106.0,
            val_pct=0.25,
            vah_pct=0.75,
        )

        assert result["val"] == 102.5
        assert result["vah"] == 107.5
        assert result["profile_long_flag"] == 1.0
