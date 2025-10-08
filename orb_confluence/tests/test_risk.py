"""Tests for risk management functions."""

from datetime import datetime

import pytest

from orb_confluence.features.opening_range import ORState
from orb_confluence.strategy.risk import (
    compute_stop,
    build_targets,
    update_be_if_needed,
)


class TestComputeStop:
    """Test compute_stop function."""

    def test_or_opposite_long(self):
        """Test OR opposite stop for long trade."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        stop = compute_stop(
            signal_direction='long',
            entry_price=100.6,
            or_state=or_state,
            stop_mode='or_opposite',
            extra_buffer=0.05,
        )

        # Stop = OR low - buffer = 100.0 - 0.05 = 99.95
        assert stop == pytest.approx(99.95, rel=0.001)

    def test_or_opposite_short(self):
        """Test OR opposite stop for short trade."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        stop = compute_stop(
            signal_direction='short',
            entry_price=99.9,
            or_state=or_state,
            stop_mode='or_opposite',
            extra_buffer=0.05,
        )

        # Stop = OR high + buffer = 100.5 + 0.05 = 100.55
        assert stop == pytest.approx(100.55, rel=0.001)

    def test_swing_mode_long(self):
        """Test swing stop for long trade."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        stop = compute_stop(
            signal_direction='long',
            entry_price=100.6,
            or_state=or_state,
            stop_mode='swing',
            extra_buffer=0.05,
            swing_low=99.5,
        )

        # Stop = swing low - buffer = 99.5 - 0.05 = 99.45
        assert stop == pytest.approx(99.45, rel=0.001)

    def test_swing_mode_short(self):
        """Test swing stop for short trade."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        stop = compute_stop(
            signal_direction='short',
            entry_price=99.9,
            or_state=or_state,
            stop_mode='swing',
            extra_buffer=0.05,
            swing_high=101.0,
        )

        # Stop = swing high + buffer = 101.0 + 0.05 = 101.05
        assert stop == pytest.approx(101.05, rel=0.001)

    def test_atr_capped_mode_long(self):
        """Test ATR-capped stop for long trade."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        # OR stop would be 99.95, ATR cap is 100.6 - 0.8*1.0 = 99.8
        # Use closer stop (higher for long) = 99.95
        stop = compute_stop(
            signal_direction='long',
            entry_price=100.6,
            or_state=or_state,
            stop_mode='atr_capped',
            extra_buffer=0.05,
            atr_value=1.0,
            atr_cap_mult=0.8,
        )

        assert stop == pytest.approx(99.95, rel=0.001)

    def test_atr_capped_mode_caps_wide_stop(self):
        """Test that ATR cap prevents too-wide stops."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=95.0,  # Very wide OR
            width=5.5,
            finalized=True,
            valid=True,
        )

        # OR stop would be 94.95, but ATR cap is 100.6 - 0.8*1.0 = 99.8
        # Use closer stop = 99.8
        stop = compute_stop(
            signal_direction='long',
            entry_price=100.6,
            or_state=or_state,
            stop_mode='atr_capped',
            extra_buffer=0.05,
            atr_value=1.0,
            atr_cap_mult=0.8,
        )

        assert stop == pytest.approx(99.8, rel=0.001)

    def test_invalid_direction(self):
        """Test that invalid direction raises error."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30),
            end_ts=datetime(2024, 1, 2, 14, 45),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        with pytest.raises(ValueError, match="Invalid direction"):
            compute_stop('up', 100.6, or_state)


class TestBuildTargets:
    """Test build_targets function."""

    def test_partials_long(self):
        """Test target construction with partials for long trade."""
        targets = build_targets(
            entry_price=100.0,
            stop_price=99.0,
            direction='long',
            partials=True,
            t1_r=1.0,
            t1_pct=0.5,
            t2_r=1.5,
            t2_pct=0.25,
            runner_r=2.0,
        )

        assert len(targets) == 3

        # T1: 100 + 1.0*1.0 = 101.0, 50%
        assert targets[0] == pytest.approx((101.0, 0.5))

        # T2: 100 + 1.5*1.0 = 101.5, 25%
        assert targets[1] == pytest.approx((101.5, 0.25))

        # Runner: 100 + 2.0*1.0 = 102.0, 25%
        assert targets[2] == pytest.approx((102.0, 0.25))

    def test_partials_short(self):
        """Test target construction with partials for short trade."""
        targets = build_targets(
            entry_price=100.0,
            stop_price=101.0,
            direction='short',
            partials=True,
            t1_r=1.0,
            t1_pct=0.5,
            t2_r=1.5,
            t2_pct=0.25,
            runner_r=2.0,
        )

        assert len(targets) == 3

        # T1: 100 - 1.0*1.0 = 99.0, 50%
        assert targets[0] == pytest.approx((99.0, 0.5))

        # T2: 100 - 1.5*1.0 = 98.5, 25%
        assert targets[1] == pytest.approx((98.5, 0.25))

        # Runner: 100 - 2.0*1.0 = 98.0, 25%
        assert targets[2] == pytest.approx((98.0, 0.25))

    def test_no_partials(self):
        """Test single target (no partials)."""
        targets = build_targets(
            entry_price=100.0,
            stop_price=99.0,
            direction='long',
            partials=False,
            primary_r=1.5,
        )

        assert len(targets) == 1

        # Single target: 100 + 1.5*1.0 = 101.5, 100%
        assert targets[0] == pytest.approx((101.5, 1.0))

    def test_invalid_risk(self):
        """Test that zero risk raises error."""
        with pytest.raises(ValueError, match="Invalid risk"):
            build_targets(100.0, 100.0, 'long')  # Entry == stop


class TestUpdateBeIfNeeded:
    """Test update_be_if_needed function."""

    def test_be_move_long(self):
        """Test breakeven move for long trade."""
        new_stop, moved = update_be_if_needed(
            entry_price=100.0,
            stop_price_current=99.0,
            direction='long',
            current_price=101.0,  # 1R achieved
            initial_risk=1.0,
            moved_to_breakeven=False,
            threshold_r=1.0,
            be_buffer=0.05,
        )

        assert new_stop == pytest.approx(100.05, rel=0.001)
        assert moved is True

    def test_be_move_short(self):
        """Test breakeven move for short trade."""
        new_stop, moved = update_be_if_needed(
            entry_price=100.0,
            stop_price_current=101.0,
            direction='short',
            current_price=99.0,  # 1R achieved
            initial_risk=1.0,
            moved_to_breakeven=False,
            threshold_r=1.0,
            be_buffer=0.05,
        )

        assert new_stop == pytest.approx(99.95, rel=0.001)
        assert moved is True

    def test_be_not_triggered(self):
        """Test that BE doesn't move before threshold."""
        new_stop, moved = update_be_if_needed(
            entry_price=100.0,
            stop_price_current=99.0,
            direction='long',
            current_price=100.5,  # Only 0.5R
            initial_risk=1.0,
            moved_to_breakeven=False,
            threshold_r=1.0,
            be_buffer=0.05,
        )

        assert new_stop == 99.0  # Unchanged
        assert moved is False

    def test_already_moved(self):
        """Test that already-moved BE doesn't change."""
        new_stop, moved = update_be_if_needed(
            entry_price=100.0,
            stop_price_current=100.05,
            direction='long',
            current_price=102.0,
            initial_risk=1.0,
            moved_to_breakeven=True,  # Already moved
            threshold_r=1.0,
            be_buffer=0.05,
        )

        assert new_stop == 100.05  # Unchanged
        assert moved is True
