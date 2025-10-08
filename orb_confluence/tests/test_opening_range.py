"""Tests for Opening Range calculation."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.features.opening_range import (
    OpeningRangeBuilder,
    ORState,
    choose_or_length,
    validate_or,
    apply_buffer,
    calculate_or_from_bars,
)


class TestOpeningRangeBuilder:
    """Test OpeningRangeBuilder class."""

    def test_basic_or_construction(self):
        """Test basic OR construction with fixed duration."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        assert builder.duration_minutes == 15
        assert builder.end_ts == start + timedelta(minutes=15)
        assert not builder.is_finalized()

    def test_update_bars(self):
        """Test updating OR with bars."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        # Create test bars
        bars = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(start=start, periods=15, freq="1min"),
                "high": [100.5, 101.0, 100.8, 101.2, 100.9] * 3,
                "low": [100.0, 100.3, 100.2, 100.5, 100.1] * 3,
            }
        )

        # Update with each bar
        for _, bar in bars.iterrows():
            builder.update(bar)

        # Check state (not finalized yet)
        state = builder.state()
        assert state.high == 101.2
        assert state.low == 100.0
        assert not state.finalized

    def test_finalization(self):
        """Test OR finalization."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        # Add bars
        bars = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(start=start, periods=15, freq="1min"),
                "high": [100.5] * 15,
                "low": [100.0] * 15,
            }
        )

        for _, bar in bars.iterrows():
            builder.update(bar)

        # Before finalization
        assert not builder.is_finalized()

        # Finalize
        end_time = start + timedelta(minutes=15)
        finalized = builder.finalize_if_due(end_time)

        assert finalized is True
        assert builder.is_finalized()

        # Check state
        state = builder.state()
        assert state.finalized is True
        assert state.valid is True
        assert state.high == 100.5
        assert state.low == 100.0
        assert state.width == 0.5

    def test_cannot_update_finalized(self):
        """Test that finalized OR cannot be updated."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        # Finalize immediately
        builder._finalize()

        # Try to update
        bar = pd.Series(
            {
                "timestamp_utc": start,
                "high": 100.5,
                "low": 100.0,
            }
        )

        with pytest.raises(ValueError, match="Cannot update finalized OR"):
            builder.update(bar)

    def test_no_bars_invalid(self):
        """Test that OR with no bars is marked invalid."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        # Finalize without any bars
        builder._finalize()

        state = builder.state()
        assert state.finalized is True
        assert state.valid is False
        assert state.invalid_reason == "No bars in OR window"

    def test_bars_outside_window_ignored(self):
        """Test that bars outside OR window are ignored."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        builder = OpeningRangeBuilder(start_ts=start, duration_minutes=15)

        # Bar before OR starts
        early_bar = pd.Series(
            {
                "timestamp_utc": start - timedelta(minutes=5),
                "high": 99.0,
                "low": 98.0,
            }
        )
        builder.update(early_bar)

        # Bar during OR
        or_bar = pd.Series(
            {
                "timestamp_utc": start + timedelta(minutes=5),
                "high": 100.5,
                "low": 100.0,
            }
        )
        builder.update(or_bar)

        # Bar after OR ends
        late_bar = pd.Series(
            {
                "timestamp_utc": start + timedelta(minutes=20),
                "high": 101.0,
                "low": 100.5,
            }
        )
        builder.update(late_bar)

        state = builder.state()
        # Should only have the OR bar
        assert state.high == 100.5
        assert state.low == 100.0


class TestAdaptiveOR:
    """Test adaptive OR duration selection."""

    def test_adaptive_low_volatility(self):
        """Test adaptive OR selects short duration for low volatility."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        # Low volatility: intraday_atr / daily_atr = 0.2 < 0.35
        builder = OpeningRangeBuilder(
            start_ts=start,
            duration_minutes=15,
            adaptive=True,
            intraday_atr=0.2,
            daily_atr=1.0,
            low_norm_vol=0.35,
            high_norm_vol=0.85,
            short_or_minutes=10,
            long_or_minutes=30,
        )

        assert builder.duration_minutes == 10

    def test_adaptive_medium_volatility(self):
        """Test adaptive OR selects base duration for medium volatility."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        # Medium volatility: 0.35 < 0.5 < 0.85
        builder = OpeningRangeBuilder(
            start_ts=start,
            duration_minutes=15,
            adaptive=True,
            intraday_atr=0.5,
            daily_atr=1.0,
            low_norm_vol=0.35,
            high_norm_vol=0.85,
            short_or_minutes=10,
            long_or_minutes=30,
        )

        assert builder.duration_minutes == 15

    def test_adaptive_high_volatility(self):
        """Test adaptive OR selects long duration for high volatility."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        # High volatility: intraday_atr / daily_atr = 1.2 > 0.85
        builder = OpeningRangeBuilder(
            start_ts=start,
            duration_minutes=15,
            adaptive=True,
            intraday_atr=1.2,
            daily_atr=1.0,
            low_norm_vol=0.35,
            high_norm_vol=0.85,
            short_or_minutes=10,
            long_or_minutes=30,
        )

        assert builder.duration_minutes == 30

    def test_adaptive_disabled(self):
        """Test that non-adaptive mode uses base duration."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        builder = OpeningRangeBuilder(
            start_ts=start,
            duration_minutes=15,
            adaptive=False,
            intraday_atr=0.2,  # Low vol, but adaptive is off
            daily_atr=1.0,
        )

        assert builder.duration_minutes == 15


class TestChooseORLength:
    """Test choose_or_length function."""

    def test_low_volatility(self):
        """Test low volatility selects short OR."""
        result = choose_or_length(
            normalized_vol=0.2, low_th=0.35, high_th=0.85, short_len=10, base_len=15, long_len=30
        )
        assert result == 10

    def test_medium_volatility(self):
        """Test medium volatility selects base OR."""
        result = choose_or_length(
            normalized_vol=0.5, low_th=0.35, high_th=0.85, short_len=10, base_len=15, long_len=30
        )
        assert result == 15

    def test_high_volatility(self):
        """Test high volatility selects long OR."""
        result = choose_or_length(
            normalized_vol=1.2, low_th=0.35, high_th=0.85, short_len=10, base_len=15, long_len=30
        )
        assert result == 30

    def test_boundary_low_threshold(self):
        """Test boundary at low threshold."""
        # Exactly at threshold (should use short)
        result = choose_or_length(
            normalized_vol=0.35,
            low_th=0.35,
            high_th=0.85,
            short_len=10,
            base_len=15,
            long_len=30,
        )
        assert result == 15  # Not less than, so base

    def test_boundary_high_threshold(self):
        """Test boundary at high threshold."""
        # Exactly at threshold (should use base)
        result = choose_or_length(
            normalized_vol=0.85,
            low_th=0.35,
            high_th=0.85,
            short_len=10,
            base_len=15,
            long_len=30,
        )
        assert result == 15  # Not greater than, so base


class TestValidateOR:
    """Test OR validation against ATR multiples."""

    def test_valid_or(self):
        """Test valid OR within ATR bounds."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        valid, reason = validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)

        assert valid is True
        assert reason is None

    def test_or_too_narrow(self):
        """Test OR too narrow (below min ATR multiple)."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.2,
            low=100.0,
            width=0.2,
            finalized=True,
            valid=True,
        )

        # width=0.2, atr=1.0 → 0.2x < 0.25x (too narrow)
        valid, reason = validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)

        assert valid is False
        assert "too narrow" in reason.lower()
        assert "0.20x" in reason

    def test_or_too_wide(self):
        """Test OR too wide (above max ATR multiple)."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=102.0,
            low=100.0,
            width=2.0,
            finalized=True,
            valid=True,
        )

        # width=2.0, atr=1.0 → 2.0x > 1.75x (too wide)
        valid, reason = validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)

        assert valid is False
        assert "too wide" in reason.lower()
        assert "2.00x" in reason

    def test_or_not_finalized(self):
        """Test validation fails if OR not finalized."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=False,  # Not finalized
            valid=True,
        )

        valid, reason = validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)

        assert valid is False
        assert "not finalized" in reason.lower()

    def test_or_already_invalid(self):
        """Test validation fails if OR already marked invalid."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=False,  # Already invalid
            invalid_reason="No bars in OR window",
        )

        valid, reason = validate_or(or_state, atr_value=1.0, min_mult=0.25, max_mult=1.75)

        assert valid is False
        assert reason == "No bars in OR window"

    def test_invalid_atr(self):
        """Test validation fails with invalid ATR."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        valid, reason = validate_or(or_state, atr_value=0.0, min_mult=0.25, max_mult=1.75)

        assert valid is False
        assert "Invalid ATR" in reason


class TestApplyBuffer:
    """Test buffer application."""

    def test_fixed_buffer(self):
        """Test fixed buffer application."""
        high, low = apply_buffer(or_high=100.5, or_low=100.0, fixed_buffer=0.05)

        assert high == 100.55
        assert low == 99.95

    def test_atr_buffer(self):
        """Test ATR-based buffer application."""
        high, low = apply_buffer(
            or_high=100.5, or_low=100.0, atr_buffer_mult=0.05, atr_value=1.0
        )

        assert high == 100.55
        assert low == 99.95

    def test_combined_buffer(self):
        """Test combined fixed + ATR buffer."""
        high, low = apply_buffer(
            or_high=100.5, or_low=100.0, fixed_buffer=0.03, atr_buffer_mult=0.02, atr_value=1.0
        )

        # 0.03 + (0.02 * 1.0) = 0.05
        assert high == 100.55
        assert low == 99.95

    def test_no_buffer(self):
        """Test no buffer (returns original values)."""
        high, low = apply_buffer(or_high=100.5, or_low=100.0)

        assert high == 100.5
        assert low == 100.0


class TestCalculateORFromBars:
    """Test batch OR calculation from bars."""

    def test_calculate_from_dataframe(self):
        """Test calculating OR from DataFrame."""
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(start=start, periods=30, freq="1min"),
                "high": [100.0 + i * 0.1 for i in range(30)],
                "low": [99.5 + i * 0.1 for i in range(30)],
            }
        )

        or_state = calculate_or_from_bars(df, session_start=start, duration_minutes=15)

        assert or_state.finalized is True
        assert or_state.valid is True
        # First 15 bars: highs from 100.0 to 101.4
        assert or_state.high == 101.4
        assert or_state.low == 99.5

    def test_missing_columns(self):
        """Test error when DataFrame missing columns."""
        df = pd.DataFrame({"timestamp_utc": [datetime.now()]})

        with pytest.raises(ValueError, match="Missing required column"):
            calculate_or_from_bars(df, session_start=datetime.now())


class TestORState:
    """Test ORState dataclass."""

    def test_midpoint_calculation(self):
        """Test OR midpoint calculation."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        assert or_state.midpoint == 100.25

    def test_repr(self):
        """Test ORState string representation."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        repr_str = repr(or_state)
        assert "✓" in repr_str
        assert "100.50" in repr_str
        assert "100.00" in repr_str