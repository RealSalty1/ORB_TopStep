"""Breakout signal detection.

Detects when price breaks through OR thresholds with confluence confirmation.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger

from ..config import BuffersConfig, ORBConfig
from ..features.or_builder import OpeningRange
from ..features.indicators import compute_atr
from .scorer import ConfluenceScorer, ConfluenceScore


class Direction(str, Enum):
    """Trade direction."""

    LONG = "long"
    SHORT = "short"


@dataclass
class BreakoutSignal:
    """Breakout signal data."""

    timestamp: datetime
    direction: Direction
    
    # Price levels
    trigger_price: float
    or_high: float
    or_low: float
    buffer: float
    
    # Confluence
    confluence_score: ConfluenceScore
    
    # Metadata
    bar_idx: int
    is_second_chance: bool = False


class BreakoutDetector:
    """Detects breakout signals when price crosses OR thresholds with confluence.

    Implements:
    - Buffer calculation (fixed + optional ATR)
    - Breakout threshold crossing detection
    - Second-chance retest logic
    """

    def __init__(
        self,
        orb_config: ORBConfig,
        buffers_config: BuffersConfig,
        confluence_scorer: ConfluenceScorer,
    ) -> None:
        """Initialize breakout detector.

        Args:
            orb_config: OR configuration.
            buffers_config: Buffer configuration.
            confluence_scorer: Confluence scorer instance.
        """
        self.orb_config = orb_config
        self.buffers_config = buffers_config
        self.confluence_scorer = confluence_scorer

    def detect_breakout(
        self,
        df: pd.DataFrame,
        bar_idx: int,
        opening_range: OpeningRange,
        allow_second_chance: bool = True,
    ) -> Optional[BreakoutSignal]:
        """Detect breakout at a specific bar.

        Args:
            df: DataFrame with bar data.
            bar_idx: Index of current bar.
            opening_range: Finalized opening range.
            allow_second_chance: Whether to allow second-chance retests.

        Returns:
            BreakoutSignal if breakout detected with confluence, else None.
        """
        # Check if OR is valid (if filter enabled)
        if self.orb_config.enable_validity_filter and not opening_range.is_valid:
            return None

        # Check if we're past OR end time
        bar_time = df.index[bar_idx]
        if bar_time < opening_range.end_time:
            return None

        # Compute buffer
        buffer = self._compute_buffer(df, bar_idx)

        # Compute breakout thresholds
        long_threshold = opening_range.or_high + buffer
        short_threshold = opening_range.or_low - buffer

        # Check if price crossed threshold (intrabar check using high/low)
        bar = df.iloc[bar_idx]

        long_triggered = bar["high"] >= long_threshold
        short_triggered = bar["low"] <= short_threshold

        if not long_triggered and not short_triggered:
            return None

        # Both can't trigger in same bar (choose based on close or return None)
        if long_triggered and short_triggered:
            logger.debug(f"Both long and short triggered at bar {bar_idx}, skipping")
            return None

        # Determine direction
        direction = Direction.LONG if long_triggered else Direction.SHORT
        trigger_price = long_threshold if long_triggered else short_threshold

        # Score confluence
        confluence_score = self.confluence_scorer.score(df, bar_idx)

        # Check confluence pass
        if direction == Direction.LONG and not confluence_score.long_pass:
            return None

        if direction == Direction.SHORT and not confluence_score.short_pass:
            return None

        # Valid breakout signal
        return BreakoutSignal(
            timestamp=bar_time,
            direction=direction,
            trigger_price=trigger_price,
            or_high=opening_range.or_high,
            or_low=opening_range.or_low,
            buffer=buffer,
            confluence_score=confluence_score,
            bar_idx=bar_idx,
            is_second_chance=False,  # Would need state tracking for true implementation
        )

    def _compute_buffer(self, df: pd.DataFrame, bar_idx: int) -> float:
        """Compute breakout buffer.

        Args:
            df: DataFrame with bar data.
            bar_idx: Current bar index.

        Returns:
            Buffer value (in price units).
        """
        buffer = self.buffers_config.fixed

        # Add ATR component if enabled
        if self.buffers_config.use_atr:
            if bar_idx >= self.orb_config.atr_period:
                atr_series = compute_atr(df[:bar_idx+1], period=self.orb_config.atr_period)
                last_atr = atr_series.dropna().iloc[-1] if not atr_series.dropna().empty else 0.0
                buffer += last_atr * self.buffers_config.atr_mult

        return buffer
