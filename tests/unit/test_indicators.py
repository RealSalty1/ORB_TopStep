"""Test technical indicators."""

import numpy as np
import pandas as pd
import pytest

from orb_strategy.features.indicators import ATR, compute_atr


def test_atr_calculation():
    """Test ATR calculation."""
    # Create synthetic OHLC data
    df = pd.DataFrame({
        "high": [102, 103, 104, 105, 106],
        "low": [98, 99, 100, 101, 102],
        "close": [100, 101, 102, 103, 104],
    })

    atr = ATR(period=3)
    result = atr.calculate(df["high"], df["low"], df["close"])

    assert len(result) == len(df)
    assert result.isna().sum() == 2  # First period-1 values are NaN
    assert result.iloc[-1] > 0  # ATR should be positive


def test_atr_with_gaps():
    """Test ATR handles gaps correctly."""
    df = pd.DataFrame({
        "high": [100, 110, 105, 103, 102],  # Gap up then down
        "low": [95, 105, 100, 98, 97],
        "close": [98, 108, 102, 100, 99],
    })

    result = compute_atr(df, period=3)

    # ATR should capture gap volatility
    assert result.iloc[-1] > 2.0  # Should be elevated


def test_atr_zero_range():
    """Test ATR with zero range bars."""
    df = pd.DataFrame({
        "high": [100] * 5,
        "low": [100] * 5,
        "close": [100] * 5,
    })

    result = compute_atr(df, period=3)

    # ATR should be zero or near-zero
    assert result.iloc[-1] < 0.01
