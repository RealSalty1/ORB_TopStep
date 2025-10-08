"""Tests for price action pattern detection."""

import numpy as np
import pandas as pd
import pytest

from orb_confluence.features.price_action import (
    detect_engulfing,
    detect_structure,
    analyze_price_action,
    analyze_price_action_batch,
)


class TestDetectEngulfing:
    """Test engulfing pattern detection."""

    def test_bullish_engulfing(self):
        """Test bullish engulfing detection."""
        # Previous: bearish (open > close)
        # Current: bullish (close > open) and engulfs previous
        bullish, bearish = detect_engulfing(
            open_curr=99.0,
            high_curr=102.0,
            low_curr=98.5,
            close_curr=101.5,
            open_prev=100.5,
            high_prev=101.0,
            low_prev=99.5,
            close_prev=100.0,
        )

        assert bullish is True
        assert bearish is False

    def test_bearish_engulfing(self):
        """Test bearish engulfing detection."""
        # Previous: bullish (close > open)
        # Current: bearish (open > close) and engulfs previous
        bullish, bearish = detect_engulfing(
            open_curr=101.5,
            high_curr=102.0,
            low_curr=98.5,
            close_curr=99.0,
            open_prev=100.0,
            high_prev=100.5,
            low_prev=99.5,
            close_prev=100.5,
        )

        assert bullish is False
        assert bearish is True

    def test_no_engulfing(self):
        """Test no engulfing pattern."""
        # Both bullish, no engulfing
        bullish, bearish = detect_engulfing(
            open_curr=100.0,
            high_curr=101.0,
            low_curr=99.5,
            close_curr=100.5,
            open_prev=99.0,
            high_prev=100.0,
            low_prev=98.5,
            close_prev=99.5,
        )

        assert bullish is False
        assert bearish is False

    def test_partial_engulfing_not_detected(self):
        """Test that partial engulfing is not detected."""
        # Current doesn't fully engulf previous
        bullish, bearish = detect_engulfing(
            open_curr=99.5,
            high_curr=101.0,
            low_curr=99.0,
            close_curr=100.5,
            open_prev=100.5,
            high_prev=101.0,
            low_prev=99.0,
            close_prev=100.0,
        )

        assert bullish is False
        assert bearish is False


class TestDetectStructure:
    """Test structure detection (HH/HL, LL/LH)."""

    def test_bullish_structure_hh_hl(self):
        """Test bullish structure (higher highs, higher lows)."""
        highs = np.array([100.0, 101.0, 102.0, 103.0])
        lows = np.array([98.0, 99.0, 100.0, 101.0])

        bullish, bearish = detect_structure(highs, lows, pivot_len=2)

        assert bullish is True
        assert bearish is False

    def test_bearish_structure_ll_lh(self):
        """Test bearish structure (lower lows, lower highs)."""
        highs = np.array([103.0, 102.0, 101.0, 100.0])
        lows = np.array([101.0, 100.0, 99.0, 98.0])

        bullish, bearish = detect_structure(highs, lows, pivot_len=2)

        assert bullish is False
        assert bearish is True

    def test_no_clear_structure(self):
        """Test no clear structure (choppy)."""
        highs = np.array([100.0, 102.0, 101.0, 103.0])
        lows = np.array([98.0, 100.0, 99.0, 101.0])

        bullish, bearish = detect_structure(highs, lows, pivot_len=2)

        # Mixed signals
        assert not (bullish and bearish)

    def test_insufficient_data(self):
        """Test insufficient data returns False."""
        highs = np.array([100.0, 101.0])
        lows = np.array([98.0, 99.0])

        bullish, bearish = detect_structure(highs, lows, pivot_len=3)

        assert bullish is False
        assert bearish is False


class TestAnalyzePriceAction:
    """Test price action analysis function."""

    def test_bullish_engulfing_detected(self):
        """Test bullish engulfing detection."""
        df = pd.DataFrame(
            {
                "open": [100.5, 99.0],
                "high": [101.0, 102.0],
                "low": [99.5, 98.5],
                "close": [100.0, 101.5],
            }
        )

        result = analyze_price_action(df, enable_engulfing=True, enable_structure=False)

        assert result["price_action_long"] == 1.0
        assert result["price_action_short"] == 0.0

    def test_bearish_engulfing_detected(self):
        """Test bearish engulfing detection."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.5],
                "high": [100.5, 102.0],
                "low": [99.5, 98.5],
                "close": [100.5, 99.0],
            }
        )

        result = analyze_price_action(df, enable_engulfing=True, enable_structure=False)

        assert result["price_action_long"] == 0.0
        assert result["price_action_short"] == 1.0

    def test_bullish_structure_detected(self):
        """Test bullish structure detection."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "high": [100.5, 101.5, 102.5, 103.5],
                "low": [99.5, 100.5, 101.5, 102.5],
                "close": [100.3, 101.3, 102.3, 103.3],
            }
        )

        result = analyze_price_action(df, pivot_len=2, enable_structure=True)

        assert result["price_action_long"] == 1.0

    def test_no_patterns_detected(self):
        """Test no patterns detected."""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [100.5],
                "low": [99.5],
                "close": [100.3],
            }
        )

        result = analyze_price_action(df)

        assert result["price_action_long"] == 0.0
        assert result["price_action_short"] == 0.0


class TestAnalyzePriceActionBatch:
    """Test batch price action analysis."""

    def test_batch_analysis(self):
        """Test batch price action analysis."""
        df = pd.DataFrame(
            {
                "open": [100.0, 100.5, 99.0, 101.0],
                "high": [100.5, 101.0, 102.0, 103.0],
                "low": [99.5, 99.5, 98.5, 100.5],
                "close": [100.3, 100.0, 101.5, 102.5],
            }
        )

        result = analyze_price_action_batch(df)

        assert "price_action_long" in result.columns
        assert "price_action_short" in result.columns
        assert len(result) == 4

    def test_batch_engulfing_detection(self):
        """Test batch engulfing detection."""
        df = pd.DataFrame(
            {
                "open": [100.5, 99.0, 100.0, 101.5],
                "high": [101.0, 102.0, 100.5, 102.0],
                "low": [99.5, 98.5, 99.5, 98.5],
                "close": [100.0, 101.5, 100.5, 99.0],
            }
        )

        result = analyze_price_action_batch(df, enable_engulfing=True, enable_structure=False)

        # Bar 1: bullish engulfing
        assert result.iloc[1]["price_action_long"] == 1.0

        # Bar 3: bearish engulfing
        assert result.iloc[3]["price_action_short"] == 1.0