"""Price action pattern detection (engulfing, structure).

Detects bullish/bearish engulfing patterns and price structure
(higher highs/higher lows vs lower lows/lower highs).
"""

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from loguru import logger


def detect_engulfing(
    open_curr: float,
    high_curr: float,
    low_curr: float,
    close_curr: float,
    open_prev: float,
    high_prev: float,
    low_prev: float,
    close_prev: float,
) -> Tuple[bool, bool]:
    """Detect bullish or bearish engulfing pattern.

    Args:
        open_curr, high_curr, low_curr, close_curr: Current bar OHLC.
        open_prev, high_prev, low_prev, close_prev: Previous bar OHLC.

    Returns:
        Tuple of (bullish_engulfing, bearish_engulfing).

    Bullish Engulfing:
    - Previous bar is bearish (close < open)
    - Current bar is bullish (close > open)
    - Current bar body engulfs previous bar body

    Bearish Engulfing:
    - Previous bar is bullish (close > open)
    - Current bar is bearish (close < open)
    - Current bar body engulfs previous bar body

    Examples:
        >>> # Bullish engulfing
        >>> detect_engulfing(100, 102, 99, 102, 101, 101.5, 100.5, 100.5)
        (True, False)

        >>> # Bearish engulfing
        >>> detect_engulfing(102, 102, 99, 99, 100, 100.5, 99.5, 100.5)
        (False, True)
    """
    # Previous bar direction
    prev_bullish = close_prev > open_prev
    prev_bearish = close_prev < open_prev

    # Current bar direction
    curr_bullish = close_curr > open_curr
    curr_bearish = close_curr < open_curr

    # Bullish engulfing
    if prev_bearish and curr_bullish:
        prev_body_high = open_prev
        prev_body_low = close_prev
        curr_body_high = close_curr
        curr_body_low = open_curr

        if curr_body_low < prev_body_low and curr_body_high > prev_body_high:
            return True, False

    # Bearish engulfing
    if prev_bullish and curr_bearish:
        prev_body_high = close_prev
        prev_body_low = open_prev
        curr_body_high = open_curr
        curr_body_low = close_curr

        if curr_body_low < prev_body_low and curr_body_high > prev_body_high:
            return False, True

    return False, False


def detect_structure(
    highs: np.ndarray,
    lows: np.ndarray,
    pivot_len: int = 3,
) -> Tuple[bool, bool]:
    """Detect price structure (HH/HL for bullish, LL/LH for bearish).

    Args:
        highs: Array of high prices (recent bars).
        lows: Array of low prices (recent bars).
        pivot_len: Number of bars to look back for pivot comparison.

    Returns:
        Tuple of (bullish_structure, bearish_structure).

    Bullish Structure (HH/HL):
    - Recent high > previous pivot high
    - Recent low > previous pivot low

    Bearish Structure (LL/LH):
    - Recent low < previous pivot low
    - Recent high < previous pivot high

    Examples:
        >>> # Uptrend: HH/HL
        >>> highs = np.array([100, 101, 102, 103])
        >>> lows = np.array([98, 99, 100, 101])
        >>> detect_structure(highs, lows, pivot_len=2)
        (True, False)

        >>> # Downtrend: LL/LH
        >>> highs = np.array([103, 102, 101, 100])
        >>> lows = np.array([101, 100, 99, 98])
        >>> detect_structure(highs, lows, pivot_len=2)
        (False, True)
    """
    if len(highs) < pivot_len + 1 or len(lows) < pivot_len + 1:
        return False, False

    # Recent vs pivot (pivot_len bars ago)
    recent_high = highs[-1]
    recent_low = lows[-1]
    pivot_high = highs[-(pivot_len + 1)]
    pivot_low = lows[-(pivot_len + 1)]

    # Bullish structure: HH and HL
    bullish = (recent_high > pivot_high) and (recent_low > pivot_low)

    # Bearish structure: LL and LH
    bearish = (recent_low < pivot_low) and (recent_high < pivot_high)

    return bullish, bearish


def analyze_price_action(
    df: pd.DataFrame,
    pivot_len: int = 3,
    enable_engulfing: bool = True,
    enable_structure: bool = True,
) -> Dict[str, float]:
    """Analyze price action for current bar.

    Args:
        df: DataFrame with OHLC columns (at least 2 rows for engulfing).
        pivot_len: Pivot lookback length for structure.
        enable_engulfing: Check for engulfing patterns.
        enable_structure: Check for structure (HH/HL, LL/LH).

    Returns:
        Dictionary with:
        - price_action_long: 1.0 if bullish signal, 0.0 otherwise
        - price_action_short: 1.0 if bearish signal, 0.0 otherwise

    Examples:
        >>> df = pd.DataFrame({
        ...     'open': [100, 99],
        ...     'high': [101, 102],
        ...     'low': [99, 98],
        ...     'close': [99.5, 101.5]
        ... })
        >>> result = analyze_price_action(df)
        >>> assert result['price_action_long'] == 1.0  # Bullish engulfing
    """
    price_action_long = 0.0
    price_action_short = 0.0

    # Engulfing patterns
    if enable_engulfing and len(df) >= 2:
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        bullish_eng, bearish_eng = detect_engulfing(
            open_curr=curr["open"],
            high_curr=curr["high"],
            low_curr=curr["low"],
            close_curr=curr["close"],
            open_prev=prev["open"],
            high_prev=prev["high"],
            low_prev=prev["low"],
            close_prev=prev["close"],
        )

        if bullish_eng:
            price_action_long = 1.0
        if bearish_eng:
            price_action_short = 1.0

    # Structure analysis
    if enable_structure and len(df) >= pivot_len + 1:
        bullish_struct, bearish_struct = detect_structure(
            highs=df["high"].values,
            lows=df["low"].values,
            pivot_len=pivot_len,
        )

        if bullish_struct:
            price_action_long = 1.0
        if bearish_struct:
            price_action_short = 1.0

    return {
        "price_action_long": price_action_long,
        "price_action_short": price_action_short,
    }


def analyze_price_action_batch(
    df: pd.DataFrame,
    pivot_len: int = 3,
    enable_engulfing: bool = True,
    enable_structure: bool = True,
) -> pd.DataFrame:
    """Analyze price action for entire DataFrame (vectorized where possible).

    Args:
        df: DataFrame with OHLC columns.
        pivot_len: Pivot lookback length.
        enable_engulfing: Check for engulfing patterns.
        enable_structure: Check for structure.

    Returns:
        DataFrame with added columns: price_action_long, price_action_short.

    Examples:
        >>> df = pd.DataFrame({
        ...     'open': [100, 99, 98, 100],
        ...     'high': [101, 100, 102, 103],
        ...     'low': [99, 98, 97, 99],
        ...     'close': [99.5, 99, 101, 102]
        ... })
        >>> result = analyze_price_action_batch(df)
        >>> assert 'price_action_long' in result.columns
    """
    df = df.copy()

    # Initialize columns
    df["price_action_long"] = 0.0
    df["price_action_short"] = 0.0

    # Engulfing detection (vectorized)
    if enable_engulfing and len(df) >= 2:
        # Shift for previous bar
        df["open_prev"] = df["open"].shift(1)
        df["close_prev"] = df["close"].shift(1)

        # Bar directions
        df["curr_bullish"] = df["close"] > df["open"]
        df["curr_bearish"] = df["close"] < df["open"]
        df["prev_bullish"] = df["close_prev"] > df["open_prev"]
        df["prev_bearish"] = df["close_prev"] < df["open_prev"]

        # Body ranges
        df["curr_body_high"] = df[["open", "close"]].max(axis=1)
        df["curr_body_low"] = df[["open", "close"]].min(axis=1)
        df["prev_body_high"] = df[["open_prev", "close_prev"]].max(axis=1)
        df["prev_body_low"] = df[["open_prev", "close_prev"]].min(axis=1)

        # Bullish engulfing
        bullish_eng = (
            df["prev_bearish"]
            & df["curr_bullish"]
            & (df["curr_body_low"] < df["prev_body_low"])
            & (df["curr_body_high"] > df["prev_body_high"])
        )
        df.loc[bullish_eng, "price_action_long"] = 1.0

        # Bearish engulfing
        bearish_eng = (
            df["prev_bullish"]
            & df["curr_bearish"]
            & (df["curr_body_low"] < df["prev_body_low"])
            & (df["curr_body_high"] > df["prev_body_high"])
        )
        df.loc[bearish_eng, "price_action_short"] = 1.0

    # Structure detection (rolling window)
    if enable_structure and len(df) >= pivot_len + 1:
        for i in range(pivot_len + 1, len(df)):
            highs = df["high"].iloc[i - pivot_len - 1 : i + 1].values
            lows = df["low"].iloc[i - pivot_len - 1 : i + 1].values

            bullish_struct, bearish_struct = detect_structure(highs, lows, pivot_len)

            if bullish_struct:
                df.iloc[i, df.columns.get_loc("price_action_long")] = 1.0
            if bearish_struct:
                df.iloc[i, df.columns.get_loc("price_action_short")] = 1.0

    # Clean up temporary columns
    temp_cols = [
        "open_prev",
        "close_prev",
        "curr_bullish",
        "curr_bearish",
        "prev_bullish",
        "prev_bearish",
        "curr_body_high",
        "curr_body_low",
        "prev_body_high",
        "prev_body_low",
    ]
    df = df.drop(columns=[col for col in temp_cols if col in df.columns])

    return df