"""Tests for breakout signal detection."""

from datetime import datetime

import pandas as pd
import pytest

from orb_confluence.features.opening_range import ORState
from orb_confluence.strategy.breakout import (
    BreakoutSignal,
    detect_breakout,
    check_intrabar_breakout,
    get_breakout_side,
)


class TestDetectBreakout:
    """Test detect_breakout function."""

    def test_long_breakout_detected(self):
        """Test long breakout detection."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.3,
            'high': 101.0,  # Breaks above
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=False,
            confluence_long_score=3.0,
            confluence_required=2.0,
            lockout=False,
        )

        assert long_sig is not None
        assert long_sig.direction == 'long'
        assert long_sig.trigger_price == 100.6
        assert long_sig.confluence_score == 3.0
        assert short_sig is None

    def test_short_breakout_detected(self):
        """Test short breakout detection."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.2,
            'high': 100.3,
            'low': 99.5,  # Breaks below
            'close': 99.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=False,
            confluence_short_pass=True,
            confluence_short_score=4.0,
            confluence_required=3.0,
            lockout=False,
        )

        assert short_sig is not None
        assert short_sig.direction == 'short'
        assert short_sig.trigger_price == 99.9
        assert short_sig.confluence_score == 4.0
        assert long_sig is None

    def test_no_breakout_within_range(self):
        """Test no breakout when price stays within range."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.2,
            'high': 100.4,  # Below upper trigger
            'low': 100.1,  # Above lower trigger
            'close': 100.3,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=True,
            lockout=False,
        )

        assert long_sig is None
        assert short_sig is None

    def test_confluence_fails_no_signal(self):
        """Test no signal when confluence fails."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.3,
            'high': 101.0,  # Would break out
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=False,  # Confluence fails
            confluence_short_pass=False,
            lockout=False,
        )

        assert long_sig is None
        assert short_sig is None

    def test_lockout_prevents_signal(self):
        """Test lockout prevents signals."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.3,
            'high': 101.0,
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=False,
            lockout=True,  # Locked out
        )

        assert long_sig is None
        assert short_sig is None

    def test_or_not_finalized(self):
        """Test no signal when OR not finalized."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=False,  # Not finalized
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.3,
            'high': 101.0,
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=False,
            lockout=False,
        )

        assert long_sig is None
        assert short_sig is None

    def test_or_invalid(self):
        """Test no signal when OR invalid."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=False,  # Invalid
            invalid_reason="Too narrow",
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.3,
            'high': 101.0,
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=False,
            lockout=False,
        )

        assert long_sig is None
        assert short_sig is None

    def test_duplicate_signal_same_bar(self):
        """Test that duplicate signal on same bar is prevented."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar_timestamp = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        bar = pd.Series({
            'timestamp_utc': bar_timestamp,
            'open': 100.3,
            'high': 101.0,
            'low': 100.2,
            'close': 100.8,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=False,
            lockout=False,
            last_signal_timestamp=bar_timestamp,  # Already signaled on this bar
        )

        assert long_sig is None
        assert short_sig is None

    def test_both_breakouts_same_bar(self):
        """Test when both long and short break out on same bar (whipsaw)."""
        or_state = ORState(
            start_ts=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            end_ts=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            high=100.5,
            low=100.0,
            width=0.5,
            finalized=True,
            valid=True,
        )

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            'open': 100.2,
            'high': 101.0,  # Breaks above
            'low': 99.5,  # Breaks below
            'close': 100.3,
        })

        long_sig, short_sig = detect_breakout(
            or_state=or_state,
            bar=bar,
            upper_trigger=100.6,
            lower_trigger=99.9,
            confluence_long_pass=True,
            confluence_short_pass=True,
            lockout=False,
        )

        # Both should signal (whipsaw scenario)
        assert long_sig is not None
        assert short_sig is not None


class TestCheckIntrabarBreakout:
    """Test check_intrabar_breakout function."""

    def test_long_breakout_only(self):
        """Test long breakout detection."""
        long_bo, short_bo = check_intrabar_breakout(
            or_high=100.5,
            or_low=100.0,
            bar_open=100.3,
            bar_high=101.0,
            bar_low=100.2,
            bar_close=100.8,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert long_bo is True
        assert short_bo is False

    def test_short_breakout_only(self):
        """Test short breakout detection."""
        long_bo, short_bo = check_intrabar_breakout(
            or_high=100.5,
            or_low=100.0,
            bar_open=100.2,
            bar_high=100.3,
            bar_low=99.5,
            bar_close=99.8,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert long_bo is False
        assert short_bo is True

    def test_both_breakouts(self):
        """Test both breakouts (whipsaw)."""
        long_bo, short_bo = check_intrabar_breakout(
            or_high=100.5,
            or_low=100.0,
            bar_open=100.2,
            bar_high=101.0,
            bar_low=99.5,
            bar_close=100.3,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert long_bo is True
        assert short_bo is True

    def test_no_breakouts(self):
        """Test no breakouts."""
        long_bo, short_bo = check_intrabar_breakout(
            or_high=100.5,
            or_low=100.0,
            bar_open=100.2,
            bar_high=100.4,
            bar_low=100.1,
            bar_close=100.3,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert long_bo is False
        assert short_bo is False


class TestGetBreakoutSide:
    """Test get_breakout_side function."""

    def test_long_side(self):
        """Test long side determination."""
        side = get_breakout_side(
            bar_open=100.3,
            bar_high=101.0,
            bar_low=100.2,
            bar_close=100.9,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert side == 'long'

    def test_short_side(self):
        """Test short side determination."""
        side = get_breakout_side(
            bar_open=100.2,
            bar_high=100.3,
            bar_low=99.5,
            bar_close=99.7,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert side == 'short'

    def test_no_side(self):
        """Test no clear side (close within range)."""
        side = get_breakout_side(
            bar_open=100.2,
            bar_high=100.4,
            bar_low=100.1,
            bar_close=100.3,
            upper_trigger=100.6,
            lower_trigger=99.9,
        )

        assert side is None