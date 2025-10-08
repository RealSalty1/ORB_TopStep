"""Factor indicators for confluence scoring.

Each factor is implemented as a class that computes signals from bar data.
All factors follow a consistent interface for integration with the scoring engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from numba import jit

from ..config import (
    RelativeVolumeConfig,
    PriceActionConfig,
    ProfileProxyConfig,
    VWAPConfig,
    ADXConfig,
)


@dataclass
class FactorSignal:
    """Factor signal output."""

    long_signal: bool
    short_signal: bool
    value: Optional[float] = None  # Raw indicator value
    metadata: Optional[dict] = None  # Additional context


class FactorIndicator(ABC):
    """Base class for factor indicators."""

    @abstractmethod
    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate factor signal for a specific bar.

        Args:
            df: DataFrame with bar data (up to and including bar_idx).
            bar_idx: Index of bar to calculate signal for.

        Returns:
            FactorSignal with long/short flags and optional metadata.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Factor name identifier."""
        pass


class RelativeVolumeIndicator(FactorIndicator):
    """Relative volume factor.

    Compares current volume to historical average (SMA).
    Signals when volume exceeds threshold multiple.
    """

    def __init__(self, config: RelativeVolumeConfig) -> None:
        """Initialize relative volume indicator.

        Args:
            config: Relative volume configuration.
        """
        self.config = config
        self.lookback = config.lookback
        self.spike_mult = config.spike_mult

    @property
    def name(self) -> str:
        """Factor name."""
        return "rel_volume"

    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate relative volume signal.

        Args:
            df: DataFrame with 'volume' column.
            bar_idx: Index of bar to calculate for.

        Returns:
            FactorSignal with spike detection.
        """
        if bar_idx < self.lookback:
            # Insufficient history
            return FactorSignal(long_signal=False, short_signal=False, value=None)

        # Get volume window
        vol_window = df["volume"].iloc[bar_idx - self.lookback : bar_idx]
        current_vol = df["volume"].iloc[bar_idx]

        # Calculate mean (handle zero volume)
        vol_mean = vol_window.mean()

        if vol_mean == 0 or np.isnan(vol_mean):
            return FactorSignal(long_signal=False, short_signal=False, value=None)

        # Relative volume
        rel_vol = current_vol / vol_mean

        # Spike detection (directional neutral - applies to both long and short)
        spike = rel_vol >= self.spike_mult

        return FactorSignal(
            long_signal=spike,
            short_signal=spike,
            value=rel_vol,
            metadata={"vol_mean": vol_mean, "spike_mult": self.spike_mult},
        )


class PriceActionIndicator(FactorIndicator):
    """Price action pattern factor.

    Detects:
    - Engulfing patterns (bullish/bearish)
    - Structure: Higher Highs/Higher Lows (bullish) or Lower Lows/Lower Highs (bearish)
    """

    def __init__(self, config: PriceActionConfig) -> None:
        """Initialize price action indicator.

        Args:
            config: Price action configuration.
        """
        self.config = config
        self.pivot_len = config.pivot_len

    @property
    def name(self) -> str:
        """Factor name."""
        return "price_action"

    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate price action signal.

        Args:
            df: DataFrame with OHLC data.
            bar_idx: Index of bar to calculate for.

        Returns:
            FactorSignal with bullish/bearish pattern detection.
        """
        long_signal = False
        short_signal = False
        metadata = {}

        # Check engulfing pattern
        if self.config.enable_engulfing and bar_idx >= 1:
            engulfing_long, engulfing_short = self._check_engulfing(df, bar_idx)
            long_signal = long_signal or engulfing_long
            short_signal = short_signal or engulfing_short
            metadata["engulfing_long"] = engulfing_long
            metadata["engulfing_short"] = engulfing_short

        # Check structure
        if self.config.enable_structure and bar_idx >= self.pivot_len:
            structure_long, structure_short = self._check_structure(df, bar_idx)
            long_signal = long_signal or structure_long
            short_signal = short_signal or structure_short
            metadata["structure_long"] = structure_long
            metadata["structure_short"] = structure_short

        return FactorSignal(
            long_signal=long_signal,
            short_signal=short_signal,
            metadata=metadata,
        )

    def _check_engulfing(self, df: pd.DataFrame, bar_idx: int) -> tuple[bool, bool]:
        """Check for engulfing patterns.

        Args:
            df: DataFrame with OHLC.
            bar_idx: Current bar index.

        Returns:
            Tuple of (bullish_engulfing, bearish_engulfing).
        """
        curr = df.iloc[bar_idx]
        prev = df.iloc[bar_idx - 1]

        # Bullish engulfing: close > prev_high AND open <= prev_close
        bullish = curr["close"] > prev["high"] and curr["open"] <= prev["close"]

        # Bearish engulfing: close < prev_low AND open >= prev_close
        bearish = curr["close"] < prev["low"] and curr["open"] >= prev["close"]

        return bullish, bearish

    def _check_structure(self, df: pd.DataFrame, bar_idx: int) -> tuple[bool, bool]:
        """Check for HH/HL (bullish) or LL/LH (bearish) structure.

        Args:
            df: DataFrame with OHLC.
            bar_idx: Current bar index.

        Returns:
            Tuple of (bullish_structure, bearish_structure).
        """
        # Get pivot window
        window = df.iloc[bar_idx - self.pivot_len : bar_idx]
        curr = df.iloc[bar_idx]

        if window.empty:
            return False, False

        pivot_high = window["high"].max()
        pivot_low = window["low"].min()

        # Bullish structure: current high > pivot high AND current low > pivot low
        bullish = curr["high"] > pivot_high and curr["low"] > pivot_low

        # Bearish structure: current low < pivot low AND current high < pivot high
        bearish = curr["low"] < pivot_low and curr["high"] < pivot_high

        return bullish, bearish


class ProfileProxyIndicator(FactorIndicator):
    """Profile proxy factor using prior day value area approximation.

    Uses quartile-based approximation:
    - VAL (Value Area Low) ≈ prior_low + 0.25 * (prior_high - prior_low)
    - VAH (Value Area High) ≈ prior_low + 0.75 * (prior_high - prior_low)
    """

    def __init__(self, config: ProfileProxyConfig) -> None:
        """Initialize profile proxy indicator.

        Args:
            config: Profile proxy configuration.
        """
        self.config = config
        self.val_pct = config.val_pct
        self.vah_pct = config.vah_pct

    @property
    def name(self) -> str:
        """Factor name."""
        return "profile_proxy"

    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate profile proxy signal.

        Args:
            df: DataFrame with OHLC and 'date' column.
            bar_idx: Index of bar to calculate for.

        Returns:
            FactorSignal with value area bias.
        """
        # Need prior day data
        curr_date = df.index[bar_idx].date()
        
        # Get prior day bars
        prior_day_df = df[df.index.date < curr_date]
        
        if prior_day_df.empty:
            return FactorSignal(long_signal=False, short_signal=False)

        # Use last available day as "prior day"
        last_day_date = prior_day_df.index[-1].date()
        prior_day = prior_day_df[prior_day_df.index.date == last_day_date]

        if prior_day.empty:
            return FactorSignal(long_signal=False, short_signal=False)

        # Compute prior day H/L
        prior_high = prior_day["high"].max()
        prior_low = prior_day["low"].min()
        prior_range = prior_high - prior_low

        if prior_range == 0:
            return FactorSignal(long_signal=False, short_signal=False)

        # Approximate value area levels
        val = prior_low + self.val_pct * prior_range
        vah = prior_low + self.vah_pct * prior_range
        mid = (prior_high + prior_low) / 2

        # Current close
        curr_close = df["close"].iloc[bar_idx]
        
        # Get OR high/low if available (simplified - would need OR context in production)
        # For now, use session open high/low
        session_start_idx = None
        for i in range(bar_idx, -1, -1):
            if df.index[i].date() == curr_date:
                session_start_idx = i
            else:
                break
        
        if session_start_idx is None:
            or_high = curr_close
            or_low = curr_close
        else:
            session_bars = df.iloc[session_start_idx : bar_idx + 1]
            or_high = session_bars["high"].max()
            or_low = session_bars["low"].min()

        # Bullish bias: close > VAH OR (OR_high > VAH AND close > MID)
        long_signal = curr_close > vah or (or_high > vah and curr_close > mid)

        # Bearish bias: close < VAL OR (OR_low < VAL AND close < MID)
        short_signal = curr_close < val or (or_low < val and curr_close < mid)

        return FactorSignal(
            long_signal=long_signal,
            short_signal=short_signal,
            metadata={
                "val": val,
                "vah": vah,
                "mid": mid,
                "prior_high": prior_high,
                "prior_low": prior_low,
            },
        )


class VWAPIndicator(FactorIndicator):
    """VWAP (Volume Weighted Average Price) factor.

    Computes session-based or OR-based VWAP and checks price alignment.
    """

    def __init__(self, config: VWAPConfig) -> None:
        """Initialize VWAP indicator.

        Args:
            config: VWAP configuration.
        """
        self.config = config

    @property
    def name(self) -> str:
        """Factor name."""
        return "vwap"

    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate VWAP signal.

        Args:
            df: DataFrame with OHLC and volume.
            bar_idx: Index of bar to calculate for.

        Returns:
            FactorSignal with VWAP alignment.
        """
        # Find session start
        curr_date = df.index[bar_idx].date()
        session_start_idx = None
        
        for i in range(bar_idx, -1, -1):
            if df.index[i].date() == curr_date:
                session_start_idx = i
            else:
                break

        if session_start_idx is None or session_start_idx == bar_idx:
            return FactorSignal(long_signal=False, short_signal=False)

        # Compute VWAP from session start
        session_bars = df.iloc[session_start_idx : bar_idx + 1]
        
        typical_price = (session_bars["high"] + session_bars["low"] + session_bars["close"]) / 3
        cum_pv = (typical_price * session_bars["volume"]).cumsum()
        cum_vol = session_bars["volume"].cumsum()

        if cum_vol.iloc[-1] == 0:
            return FactorSignal(long_signal=False, short_signal=False)

        vwap = cum_pv.iloc[-1] / cum_vol.iloc[-1]
        curr_close = df["close"].iloc[bar_idx]

        # Alignment
        long_signal = curr_close > vwap
        short_signal = curr_close < vwap

        return FactorSignal(
            long_signal=long_signal,
            short_signal=short_signal,
            value=vwap,
            metadata={"vwap": vwap},
        )


class ADXIndicator(FactorIndicator):
    """ADX (Average Directional Index) trend regime factor.

    Manual implementation using Wilder's smoothing.
    """

    def __init__(self, config: ADXConfig) -> None:
        """Initialize ADX indicator.

        Args:
            config: ADX configuration.
        """
        self.config = config
        self.period = config.period
        self.threshold = config.threshold

    @property
    def name(self) -> str:
        """Factor name."""
        return "adx"

    def calculate(self, df: pd.DataFrame, bar_idx: int) -> FactorSignal:
        """Calculate ADX signal.

        Args:
            df: DataFrame with OHLC.
            bar_idx: Index of bar to calculate for.

        Returns:
            FactorSignal with trend strength.
        """
        if bar_idx < self.period * 2:
            return FactorSignal(long_signal=False, short_signal=False)

        # Get window for calculation
        window = df.iloc[max(0, bar_idx - self.period * 3) : bar_idx + 1]

        # Compute ADX
        adx_series = self._compute_adx(window)

        if adx_series.empty or np.isnan(adx_series.iloc[-1]):
            return FactorSignal(long_signal=False, short_signal=False)

        adx_value = adx_series.iloc[-1]

        # ADX above threshold indicates trend (applies to both directions)
        trend_present = adx_value >= self.threshold

        return FactorSignal(
            long_signal=trend_present,
            short_signal=trend_present,
            value=adx_value,
            metadata={"adx": adx_value, "threshold": self.threshold},
        )

    def _compute_adx(self, df: pd.DataFrame) -> pd.Series:
        """Compute ADX using Wilder's smoothing.

        Args:
            df: DataFrame with OHLC.

        Returns:
            Series of ADX values.
        """
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        # Compute directional movement
        dm_plus, dm_minus, tr = self._directional_movement(high, low, close)

        # Apply Wilder's smoothing
        dm_plus_smooth = self._wilder_smooth(dm_plus, self.period)
        dm_minus_smooth = self._wilder_smooth(dm_minus, self.period)
        tr_smooth = self._wilder_smooth(tr, self.period)

        # Compute DI+ and DI-
        di_plus = 100 * dm_plus_smooth / tr_smooth
        di_minus = 100 * dm_minus_smooth / tr_smooth

        # Compute DX
        dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus)
        dx = np.nan_to_num(dx, nan=0.0)

        # Compute ADX (smoothed DX)
        adx = self._wilder_smooth(dx, self.period)

        return pd.Series(adx, index=df.index, name="ADX")

    @staticmethod
    @jit(nopython=True)
    def _directional_movement(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute directional movement and true range.

        Args:
            high: High prices.
            low: Low prices.
            close: Close prices.

        Returns:
            Tuple of (+DM, -DM, TR) arrays.
        """
        n = len(high)
        dm_plus = np.zeros(n, dtype=np.float64)
        dm_minus = np.zeros(n, dtype=np.float64)
        tr = np.zeros(n, dtype=np.float64)

        # First bar
        tr[0] = high[0] - low[0]

        for i in range(1, n):
            # Directional movement
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]

            if up_move > down_move and up_move > 0:
                dm_plus[i] = up_move
            else:
                dm_plus[i] = 0

            if down_move > up_move and down_move > 0:
                dm_minus[i] = down_move
            else:
                dm_minus[i] = 0

            # True range
            hl = high[i] - low[i]
            hc = np.abs(high[i] - close[i - 1])
            lc = np.abs(low[i] - close[i - 1])
            tr[i] = max(hl, hc, lc)

        return dm_plus, dm_minus, tr

    @staticmethod
    @jit(nopython=True)
    def _wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
        """Apply Wilder's smoothing (RMA).

        Args:
            values: Input values.
            period: Smoothing period.

        Returns:
            Smoothed array.
        """
        n = len(values)
        smoothed = np.zeros(n, dtype=np.float64)

        if n >= period:
            # Initialize with SMA
            smoothed[period - 1] = np.mean(values[:period])

            # Apply Wilder's smoothing
            for i in range(period, n):
                smoothed[i] = (smoothed[i - 1] * (period - 1) + values[i]) / period
        else:
            smoothed[:] = np.nan

        smoothed[: period - 1] = np.nan

        return smoothed
