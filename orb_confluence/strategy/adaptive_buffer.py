"""Adaptive buffer calculation for breakout entries.

Buffer = base_points + volatility_scalar * std(recent_returns) + liquidity_adjustment

This prevents entries on noise while allowing genuine breakouts.
"""

import numpy as np
import pandas as pd
from typing import Tuple
from loguru import logger


class AdaptiveBufferCalculator:
    """Calculate adaptive entry buffers based on recent volatility."""
    
    def __init__(
        self,
        instrument_config,
        lookback_bars: int = 10
    ):
        """Initialize buffer calculator.
        
        Args:
            instrument_config: InstrumentConfig object with buffer settings
            lookback_bars: Number of recent bars for volatility calculation
        """
        self.config = instrument_config
        self.lookback_bars = lookback_bars
        
        # Recent price history for volatility calculation
        self.recent_closes = []
    
    def update(self, close_price: float):
        """Update with new bar's close price."""
        self.recent_closes.append(close_price)
        
        # Keep only needed history
        if len(self.recent_closes) > self.lookback_bars + 1:
            self.recent_closes.pop(0)
    
    def calculate_buffer(self) -> Tuple[float, float]:
        """Calculate adaptive long and short buffers.
        
        Returns:
            Tuple of (long_buffer, short_buffer) in points
        """
        # Base buffer from config
        base_buffer = self.config.buffer_base_points
        
        # Calculate recent volatility
        if len(self.recent_closes) < 2:
            # Not enough data, use base buffer
            volatility_component = 0.0
        else:
            # Calculate 1-bar returns
            returns = []
            for i in range(1, len(self.recent_closes)):
                ret = abs(self.recent_closes[i] - self.recent_closes[i-1])
                returns.append(ret)
            
            # Standard deviation of recent price changes
            if len(returns) > 0:
                vol_std = float(np.std(returns))
            else:
                vol_std = 0.0
            
            # Scale by config multiplier
            volatility_component = self.config.buffer_volatility_scalar * vol_std
        
        # Total buffer
        total_buffer = base_buffer + volatility_component
        
        # Apply min/max caps from config
        capped_buffer = np.clip(
            total_buffer,
            self.config.buffer_min,
            self.config.buffer_max
        )
        
        logger.debug(
            f"{self.config.symbol}: buffer = {base_buffer:.4f} (base) + "
            f"{volatility_component:.4f} (vol) = {capped_buffer:.4f} (capped)"
        )
        
        # For now, symmetric buffers (could make asymmetric based on bias)
        return capped_buffer, capped_buffer
    
    def get_breakout_levels(
        self,
        or_high: float,
        or_low: float
    ) -> Tuple[float, float]:
        """Get breakout trigger levels.
        
        Args:
            or_high: Opening range high
            or_low: Opening range low
        
        Returns:
            Tuple of (long_trigger, short_trigger) prices
        """
        long_buffer, short_buffer = self.calculate_buffer()
        
        long_trigger = or_high + long_buffer
        short_trigger = or_low - short_buffer
        
        return long_trigger, short_trigger
    
    def get_current_buffer_info(self) -> dict:
        """Get current buffer information for logging."""
        long_buf, short_buf = self.calculate_buffer()
        
        return {
            'long_buffer': long_buf,
            'short_buffer': short_buf,
            'base_buffer': self.config.buffer_base_points,
            'min_buffer': self.config.buffer_min,
            'max_buffer': self.config.buffer_max,
            'volatility_scalar': self.config.buffer_volatility_scalar,
            'recent_bars_count': len(self.recent_closes)
        }


def create_buffer_calculator(instrument_config, lookback_bars: int = 10) -> AdaptiveBufferCalculator:
    """Factory function to create buffer calculator from config."""
    return AdaptiveBufferCalculator(
        instrument_config=instrument_config,
        lookback_bars=lookback_bars
    )


class BreakoutDetector:
    """Detect breakouts with adaptive buffers and retest logic."""
    
    def __init__(
        self,
        instrument_config,
        buffer_calculator: AdaptiveBufferCalculator
    ):
        """Initialize breakout detector.
        
        Args:
            instrument_config: InstrumentConfig object
            buffer_calculator: AdaptiveBufferCalculator instance
        """
        self.config = instrument_config
        self.buffer_calc = buffer_calculator
        
        # Track if we've had a wick-only break
        self.pending_retest_long = False
        self.pending_retest_short = False
        self.last_wick_high = None
        self.last_wick_low = None
    
    def detect(
        self,
        or_high: float,
        or_low: float,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        timestamp
    ) -> Tuple[bool, bool, dict]:
        """Detect breakout on current bar.
        
        Args:
            or_high: OR high
            or_low: OR low
            bar_open, bar_high, bar_low, bar_close: Current bar OHLC
            timestamp: Bar timestamp
        
        Returns:
            Tuple of (long_signal, short_signal, signal_info)
        """
        # Get adaptive trigger levels
        long_trigger, short_trigger = self.buffer_calc.get_breakout_levels(or_high, or_low)
        
        signal_info = {
            'long_trigger': long_trigger,
            'short_trigger': short_trigger,
            'had_wick_break': False,
            'is_retest': False,
            'timestamp': timestamp
        }
        
        long_signal = False
        short_signal = False
        
        # Check for long breakout
        if bar_high > long_trigger:
            if bar_close > long_trigger:
                # Body close beyond trigger - immediate signal
                long_signal = True
                signal_info['breakout_type'] = 'body_close'
                self.pending_retest_long = False
            else:
                # Wick-only - mark for retest
                signal_info['had_wick_break'] = True
                signal_info['breakout_type'] = 'wick_only'
                self.pending_retest_long = True
                self.last_wick_high = bar_high
                logger.info(
                    f"{self.config.symbol}: Long wick-only break at {bar_high:.2f}, "
                    f"waiting for retest"
                )
        
        # Check for retest confirmation (if we had a prior wick)
        elif self.pending_retest_long and bar_high >= long_trigger:
            if bar_close > long_trigger:
                # Retest confirmed with body close
                long_signal = True
                signal_info['is_retest'] = True
                signal_info['breakout_type'] = 'retest_confirmed'
                self.pending_retest_long = False
                logger.info(
                    f"{self.config.symbol}: Long retest confirmed at {bar_close:.2f}"
                )
        
        # Check for short breakout
        if bar_low < short_trigger:
            if bar_close < short_trigger:
                # Body close beyond trigger - immediate signal
                short_signal = True
                signal_info['breakout_type'] = 'body_close'
                self.pending_retest_short = False
            else:
                # Wick-only - mark for retest
                signal_info['had_wick_break'] = True
                signal_info['breakout_type'] = 'wick_only'
                self.pending_retest_short = True
                self.last_wick_low = bar_low
                logger.info(
                    f"{self.config.symbol}: Short wick-only break at {bar_low:.2f}, "
                    f"waiting for retest"
                )
        
        # Check for retest confirmation (if we had a prior wick)
        elif self.pending_retest_short and bar_low <= short_trigger:
            if bar_close < short_trigger:
                # Retest confirmed with body close
                short_signal = True
                signal_info['is_retest'] = True
                signal_info['breakout_type'] = 'retest_confirmed'
                self.pending_retest_short = False
                logger.info(
                    f"{self.config.symbol}: Short retest confirmed at {bar_close:.2f}"
                )
        
        return long_signal, short_signal, signal_info
    
    def reset(self):
        """Reset retest flags (e.g., at end of day)."""
        self.pending_retest_long = False
        self.pending_retest_short = False
        self.last_wick_high = None
        self.last_wick_low = None
