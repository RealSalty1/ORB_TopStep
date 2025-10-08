"""Synthetic data generator for testing and stress scenarios."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from .base import DataProvider


class VolatilityRegime(str, Enum):
    """Volatility regime types."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SPIKE = "spike"


class TrendType(str, Enum):
    """Trend types."""

    NONE = "none"
    BULLISH = "bullish"
    BEARISH = "bearish"
    MEAN_REVERTING = "mean_reverting"


class SyntheticProvider(DataProvider):
    """Synthetic data generator for controlled testing scenarios.

    Generates realistic OHLCV bars with configurable volatility regimes,
    trend characteristics, and volume patterns. Useful for stress testing
    strategy logic and edge case validation.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """Initialize synthetic provider.

        Args:
            seed: Random seed for reproducibility.
        """
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    @property
    def name(self) -> str:
        """Provider name."""
        return "synthetic"

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Generate synthetic OHLCV bars.

        Args:
            symbol: Synthetic symbol identifier.
            start: Start datetime (UTC).
            end: End datetime (UTC).
            interval: Bar interval (only '1m' supported currently).

        Returns:
            DataFrame with standardized schema.

        Raises:
            ValueError: If interval is unsupported or parameters invalid.
        """
        if interval != "1m":
            raise ValueError(f"Synthetic provider only supports '1m' interval, got {interval}")

        if start >= end:
            raise ValueError(f"start ({start}) must be before end ({end})")

        logger.info(f"Generating synthetic data for {symbol}: {start} to {end}")

        # Generate minute timestamps
        timestamps = pd.date_range(start=start, end=end, freq="1min", tz="UTC")
        n_bars = len(timestamps)

        # Parse symbol to extract regime hints (e.g., "SYN_LOW_BULL")
        volatility_regime, trend_type = self._parse_symbol(symbol)

        # Generate price series
        prices = self._generate_prices(
            n_bars=n_bars,
            base_price=100.0,
            volatility_regime=volatility_regime,
            trend_type=trend_type,
        )

        # Generate OHLC from price series
        ohlc = self._generate_ohlc(prices)

        # Generate volume
        volume = self._generate_volume(
            n_bars=n_bars,
            base_volume=10000.0,
            volatility_regime=volatility_regime,
        )

        # Create DataFrame
        df = pd.DataFrame(
            {
                "timestamp": timestamps[:n_bars],
                "open": ohlc["open"],
                "high": ohlc["high"],
                "low": ohlc["low"],
                "close": ohlc["close"],
                "volume": volume,
                "symbol": symbol,
                "source": self.name,
            }
        )

        df = df.set_index("timestamp").sort_index()

        logger.info(f"Generated {len(df)} synthetic bars for {symbol}")

        return df

    def validate_symbol(self, symbol: str) -> bool:
        """Synthetic symbols always valid (generated on demand).

        Args:
            symbol: Symbol identifier.

        Returns:
            Always True.
        """
        return True

    def _parse_symbol(self, symbol: str) -> tuple[VolatilityRegime, TrendType]:
        """Parse synthetic symbol to extract regime hints.

        Args:
            symbol: Symbol string (e.g., 'SYN_HIGH_BULL').

        Returns:
            Tuple of (volatility_regime, trend_type).
        """
        parts = symbol.upper().split("_")

        # Default regime
        volatility_regime = VolatilityRegime.MEDIUM
        trend_type = TrendType.NONE

        # Parse volatility
        if "LOW" in parts:
            volatility_regime = VolatilityRegime.LOW
        elif "HIGH" in parts:
            volatility_regime = VolatilityRegime.HIGH
        elif "SPIKE" in parts:
            volatility_regime = VolatilityRegime.SPIKE

        # Parse trend
        if "BULL" in parts or "BULLISH" in parts:
            trend_type = TrendType.BULLISH
        elif "BEAR" in parts or "BEARISH" in parts:
            trend_type = TrendType.BEARISH
        elif "MEAN" in parts or "REVERTING" in parts:
            trend_type = TrendType.MEAN_REVERTING

        return volatility_regime, trend_type

    def _generate_prices(
        self,
        n_bars: int,
        base_price: float,
        volatility_regime: VolatilityRegime,
        trend_type: TrendType,
    ) -> np.ndarray:
        """Generate synthetic price series.

        Args:
            n_bars: Number of bars.
            base_price: Starting price.
            volatility_regime: Volatility regime.
            trend_type: Trend type.

        Returns:
            Array of closing prices.
        """
        # Set volatility (annualized %)
        vol_map = {
            VolatilityRegime.LOW: 0.10,
            VolatilityRegime.MEDIUM: 0.20,
            VolatilityRegime.HIGH: 0.40,
            VolatilityRegime.SPIKE: 0.80,
        }
        annual_vol = vol_map[volatility_regime]

        # Convert to per-bar volatility (assuming 252 days, 390 minutes per day)
        bars_per_year = 252 * 390
        bar_vol = annual_vol / np.sqrt(bars_per_year)

        # Generate random returns
        returns = self._rng.normal(0, bar_vol, n_bars)

        # Add trend drift
        if trend_type == TrendType.BULLISH:
            drift = 0.0001  # Slight upward drift per bar
            returns += drift
        elif trend_type == TrendType.BEARISH:
            drift = -0.0001
            returns += drift
        elif trend_type == TrendType.MEAN_REVERTING:
            # Mean reversion: negative correlation with distance from base
            prices_temp = base_price * np.exp(np.cumsum(returns))
            mean_reversion_strength = 0.001
            returns -= mean_reversion_strength * (prices_temp - base_price) / base_price

        # Convert returns to prices
        prices = base_price * np.exp(np.cumsum(returns))

        return prices

    def _generate_ohlc(self, closes: np.ndarray) -> dict[str, np.ndarray]:
        """Generate OHLC from close prices.

        Args:
            closes: Array of closing prices.

        Returns:
            Dict with 'open', 'high', 'low', 'close' arrays.
        """
        n = len(closes)

        # Open is previous close (shifted)
        opens = np.concatenate([[closes[0]], closes[:-1]])

        # Generate intrabar range
        avg_range_pct = 0.001  # ~0.1% typical intrabar range
        ranges = np.abs(self._rng.normal(avg_range_pct, avg_range_pct / 2, n))

        # High/Low around open-close range
        highs = np.maximum(opens, closes) * (1 + ranges / 2)
        lows = np.minimum(opens, closes) * (1 - ranges / 2)

        return {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        }

    def _generate_volume(
        self,
        n_bars: int,
        base_volume: float,
        volatility_regime: VolatilityRegime,
    ) -> np.ndarray:
        """Generate volume with realistic patterns.

        Args:
            n_bars: Number of bars.
            base_volume: Base volume level.
            volatility_regime: Volatility regime (affects volume variability).

        Returns:
            Array of volume values.
        """
        # Higher volatility typically means higher volume variability
        vol_variability_map = {
            VolatilityRegime.LOW: 0.3,
            VolatilityRegime.MEDIUM: 0.5,
            VolatilityRegime.HIGH: 0.8,
            VolatilityRegime.SPIKE: 1.5,
        }
        variability = vol_variability_map[volatility_regime]

        # Generate volume with log-normal distribution
        volume = self._rng.lognormal(
            mean=np.log(base_volume),
            sigma=variability,
            size=n_bars,
        )

        # Add time-of-day pattern (higher volume at open/close)
        if n_bars >= 390:  # At least one trading day
            bars_per_day = 390
            for day_start in range(0, n_bars, bars_per_day):
                day_end = min(day_start + bars_per_day, n_bars)
                day_bars = day_end - day_start

                # U-shaped volume pattern
                time_factor = np.linspace(0, 1, day_bars)
                u_shape = 1 + 0.5 * (time_factor**2 + (1 - time_factor) ** 2)
                
                volume[day_start:day_end] *= u_shape

        return volume
