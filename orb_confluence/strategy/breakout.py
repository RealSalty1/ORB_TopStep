"""Breakout signal detection with confluence gating.

Detects when price breaches Opening Range boundaries with optional
buffers, subject to confluence scoring and governance rules.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
from loguru import logger

from ..features.opening_range import ORState


@dataclass
class BreakoutSignal:
    """Breakout signal with metadata."""

    timestamp: datetime
    direction: str  # 'long' or 'short'
    trigger_price: float  # Price that triggered breakout
    or_high: float
    or_low: float
    or_width: float
    confluence_score: float
    confluence_required: float
    signal_id: str  # Unique identifier

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"BreakoutSignal({self.direction.upper()} @ {self.timestamp.time()}, "
            f"trigger={self.trigger_price:.2f}, score={self.confluence_score:.1f}/"
            f"{self.confluence_required:.1f})"
        )


def detect_breakout(
    or_state: ORState,
    bar: pd.Series,
    upper_trigger: float,
    lower_trigger: float,
    confluence_long_pass: bool,
    confluence_short_pass: bool,
    confluence_long_score: float = 0.0,
    confluence_short_score: float = 0.0,
    confluence_required: float = 0.0,
    lockout: bool = False,
    last_signal_timestamp: Optional[datetime] = None,
) -> Tuple[Optional[BreakoutSignal], Optional[BreakoutSignal]]:
    """Detect breakout signals with confluence gating.

    Args:
        or_state: Opening Range state (must be finalized and valid).
        bar: Current bar with timestamp_utc, open, high, low, close.
        upper_trigger: Upper breakout trigger (OR high + buffer).
        lower_trigger: Lower breakout trigger (OR low - buffer).
        confluence_long_pass: Whether long confluence passes.
        confluence_short_pass: Whether short confluence passes.
        confluence_long_score: Long confluence score (for metadata).
        confluence_short_score: Short confluence score (for metadata).
        confluence_required: Required confluence score (for metadata).
        lockout: Whether signals are locked out (governance).
        last_signal_timestamp: Timestamp of last signal (prevents duplicates on same bar).

    Returns:
        Tuple of (long_signal, short_signal). Each is BreakoutSignal or None.

    Notes:
        - Uses bar.high for long breakout, bar.low for short breakout (intrabar)
        - Prevents duplicate signals on same bar
        - Requires OR to be finalized and valid
        - Requires confluence to pass
        - Respects lockout status

    Examples:
        >>> or_state = ORState(
        ...     start_ts=datetime(2024, 1, 2, 14, 30),
        ...     end_ts=datetime(2024, 1, 2, 14, 45),
        ...     high=100.5, low=100.0, width=0.5,
        ...     finalized=True, valid=True
        ... )
        >>> bar = pd.Series({
        ...     'timestamp_utc': datetime(2024, 1, 2, 15, 0),
        ...     'open': 100.3, 'high': 101.0, 'low': 100.2, 'close': 100.8
        ... })
        >>> long_sig, short_sig = detect_breakout(
        ...     or_state, bar, upper_trigger=100.6, lower_trigger=99.9,
        ...     confluence_long_pass=True, confluence_short_pass=False,
        ...     lockout=False
        ... )
        >>> assert long_sig is not None
        >>> assert long_sig.direction == 'long'
    """
    long_signal = None
    short_signal = None

    # Check preconditions
    if not or_state.finalized:
        logger.debug("OR not finalized, no breakout detection")
        return None, None

    if not or_state.valid:
        logger.debug(f"OR invalid ({or_state.invalid_reason}), no breakout detection")
        return None, None

    if lockout:
        logger.debug("Lockout active, no breakout signals")
        return None, None

    # Prevent duplicate signals on same bar
    bar_timestamp = bar['timestamp_utc']
    if last_signal_timestamp is not None and bar_timestamp == last_signal_timestamp:
        logger.debug(f"Already signaled on bar {bar_timestamp}, skipping duplicate")
        return None, None

    # Detect long breakout (price breaks above upper trigger)
    if bar['high'] > upper_trigger and confluence_long_pass:
        trigger_price = upper_trigger  # Use trigger as entry price
        signal_id = f"LONG_{bar_timestamp.strftime('%Y%m%d_%H%M%S')}"

        long_signal = BreakoutSignal(
            timestamp=bar_timestamp,
            direction='long',
            trigger_price=trigger_price,
            or_high=or_state.high,
            or_low=or_state.low,
            or_width=or_state.width,
            confluence_score=confluence_long_score,
            confluence_required=confluence_required,
            signal_id=signal_id,
        )

        logger.info(
            f"LONG breakout: bar.high={bar['high']:.2f} > trigger={upper_trigger:.2f}, "
            f"confluence={confluence_long_score:.1f}/{confluence_required:.1f}"
        )

    # Detect short breakout (price breaks below lower trigger)
    if bar['low'] < lower_trigger and confluence_short_pass:
        trigger_price = lower_trigger  # Use trigger as entry price
        signal_id = f"SHORT_{bar_timestamp.strftime('%Y%m%d_%H%M%S')}"

        short_signal = BreakoutSignal(
            timestamp=bar_timestamp,
            direction='short',
            trigger_price=trigger_price,
            or_high=or_state.high,
            or_low=or_state.low,
            or_width=or_state.width,
            confluence_score=confluence_short_score,
            confluence_required=confluence_required,
            signal_id=signal_id,
        )

        logger.info(
            f"SHORT breakout: bar.low={bar['low']:.2f} < trigger={lower_trigger:.2f}, "
            f"confluence={confluence_short_score:.1f}/{confluence_required:.1f}"
        )

    return long_signal, short_signal


def check_intrabar_breakout(
    or_high: float,
    or_low: float,
    bar_open: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    upper_trigger: float,
    lower_trigger: float,
) -> Tuple[bool, bool]:
    """Check if breakout occurred within bar (uses high/low).

    Args:
        or_high: OR high.
        or_low: OR low.
        bar_open: Bar open price.
        bar_high: Bar high price.
        bar_low: Bar low price.
        bar_close: Bar close price.
        upper_trigger: Upper breakout trigger.
        lower_trigger: Lower breakout trigger.

    Returns:
        Tuple of (long_breakout, short_breakout) booleans.

    Notes:
        - Long breakout if bar.high > upper_trigger
        - Short breakout if bar.low < lower_trigger
        - Both can trigger on same bar (whipsaw)

    Examples:
        >>> long_bo, short_bo = check_intrabar_breakout(
        ...     or_high=100.5, or_low=100.0,
        ...     bar_open=100.3, bar_high=101.0, bar_low=99.5, bar_close=100.2,
        ...     upper_trigger=100.6, lower_trigger=99.9
        ... )
        >>> assert long_bo is True  # high 101.0 > 100.6
        >>> assert short_bo is True  # low 99.5 < 99.9
    """
    long_breakout = bar_high > upper_trigger
    short_breakout = bar_low < lower_trigger

    return long_breakout, short_breakout


def get_breakout_side(
    bar_open: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    upper_trigger: float,
    lower_trigger: float,
) -> Optional[str]:
    """Determine breakout side based on close relative to OR.

    Args:
        bar_open: Bar open.
        bar_high: Bar high.
        bar_low: Bar low.
        bar_close: Bar close.
        upper_trigger: Upper trigger.
        lower_trigger: Lower trigger.

    Returns:
        'long' if close above upper trigger, 'short' if below lower trigger, None otherwise.

    Examples:
        >>> side = get_breakout_side(100.3, 101.0, 100.2, 100.9, 100.6, 99.9)
        >>> assert side == 'long'  # close 100.9 > 100.6
    """
    if bar_close > upper_trigger:
        return 'long'
    elif bar_close < lower_trigger:
        return 'short'
    else:
        return None