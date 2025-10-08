"""Synthetic data generator with deterministic, reproducible output."""

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class SyntheticProvider:
    """Synthetic data generator for controlled testing scenarios.

    Generates deterministic minute bars with configurable:
    - Volatility regimes (for narrow/wide OR testing)
    - Trend direction
    - Volume profiles
    - Price ranges
    """

    def __init__(self) -> None:
        """Initialize synthetic provider."""
        self.name = "synthetic"

    def generate_synthetic_day(
        self,
        seed: int,
        regime: str = "trend_up",
        minutes: int = 390,
        base_price: float = 100.0,
        vol_profile: str = "u_shape",
        volatility_mult: float = 1.0,
    ) -> pd.DataFrame:
        """Generate deterministic synthetic minute bars for one trading day.

        Args:
            seed: Random seed for reproducibility.
            regime: Price regime - 'trend_up', 'trend_down', 'mean_revert', 'choppy'.
            minutes: Number of minutes to generate (default 390 = full trading day).
            base_price: Starting price level.
            vol_profile: Volume profile - 'u_shape', 'flat', 'morning_spike'.
            volatility_mult: Volatility multiplier (>1 = wider OR, <1 = narrower OR).

        Returns:
            DataFrame with timestamp_utc, open, high, low, close, volume, symbol, source.

        Examples:
            >>> # Generate reproducible data
            >>> df1 = provider.generate_synthetic_day(seed=42, regime='trend_up')
            >>> df2 = provider.generate_synthetic_day(seed=42, regime='trend_up')
            >>> assert df1.equals(df2)  # Identical output

            >>> # Test narrow OR scenario
            >>> df_narrow = provider.generate_synthetic_day(seed=123, volatility_mult=0.3)

            >>> # Test wide OR scenario
            >>> df_wide = provider.generate_synthetic_day(seed=123, volatility_mult=2.5)
        """
        # Set seed for reproducibility
        rng = np.random.default_rng(seed)

        logger.debug(
            f"Generating synthetic day: regime={regime}, minutes={minutes}, "
            f"volatility_mult={volatility_mult}"
        )

        # Generate timestamps (default to a trading day starting at 9:30 AM UTC)
        start_time = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)  # 9:30 ET
        timestamps = pd.date_range(start=start_time, periods=minutes, freq="1min", tz="UTC")

        # Generate price series based on regime
        prices = self._generate_prices(rng, minutes, base_price, regime, volatility_mult)

        # Generate OHLC from close prices
        ohlc = self._generate_ohlc(rng, prices, volatility_mult)

        # Generate volume based on profile
        volume = self._generate_volume(rng, minutes, vol_profile)

        # Create DataFrame
        df = pd.DataFrame(
            {
                "timestamp_utc": timestamps,
                "open": ohlc["open"],
                "high": ohlc["high"],
                "low": ohlc["low"],
                "close": ohlc["close"],
                "volume": volume,
                "symbol": f"SYN_{regime.upper()}",
                "source": self.name,
            }
        )

        logger.info(f"Generated {len(df)} synthetic bars for {regime} regime")

        return df

    def _generate_prices(
        self,
        rng: np.random.Generator,
        n_bars: int,
        base_price: float,
        regime: str,
        volatility_mult: float,
    ) -> np.ndarray:
        """Generate price series based on regime.

        Args:
            rng: Random number generator.
            n_bars: Number of bars.
            base_price: Starting price.
            regime: Price regime.
            volatility_mult: Volatility multiplier.

        Returns:
            Array of closing prices.
        """
        # Base volatility (per-bar standard deviation as % of price)
        base_vol = 0.0015 * volatility_mult  # ~0.15% per minute

        # Generate returns based on regime
        if regime == "trend_up":
            drift = 0.0002  # Slight upward drift
            returns = rng.normal(drift, base_vol, n_bars)

        elif regime == "trend_down":
            drift = -0.0002  # Slight downward drift
            returns = rng.normal(drift, base_vol, n_bars)

        elif regime == "mean_revert":
            # Mean reverting: negative correlation with distance from base
            returns = rng.normal(0, base_vol, n_bars)
            prices_temp = base_price * np.exp(np.cumsum(returns))
            mean_reversion_strength = 0.002
            returns -= mean_reversion_strength * (prices_temp - base_price) / base_price

        elif regime == "choppy":
            # Higher volatility, no trend
            returns = rng.normal(0, base_vol * 1.5, n_bars)

        else:
            # Default: random walk
            returns = rng.normal(0, base_vol, n_bars)

        # Convert returns to prices
        prices = base_price * np.exp(np.cumsum(returns))

        return prices

    def _generate_ohlc(
        self,
        rng: np.random.Generator,
        closes: np.ndarray,
        volatility_mult: float,
    ) -> dict[str, np.ndarray]:
        """Generate OHLC from close prices.

        Args:
            rng: Random number generator.
            closes: Array of closing prices.
            volatility_mult: Volatility multiplier.

        Returns:
            Dict with 'open', 'high', 'low', 'close' arrays.
        """
        n = len(closes)

        # Open is previous close (shifted)
        opens = np.concatenate([[closes[0]], closes[:-1]])

        # Generate intrabar range (as percentage)
        avg_range_pct = 0.001 * volatility_mult  # ~0.1% typical intrabar range
        ranges = np.abs(rng.normal(avg_range_pct, avg_range_pct / 3, n))

        # High/Low around open-close range
        highs = np.maximum(opens, closes) * (1 + ranges / 2)
        lows = np.minimum(opens, closes) * (1 - ranges / 2)

        # Ensure OHLC validity
        highs = np.maximum(highs, np.maximum(opens, closes))
        lows = np.minimum(lows, np.minimum(opens, closes))

        return {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        }

    def _generate_volume(
        self,
        rng: np.random.Generator,
        n_bars: int,
        vol_profile: str,
    ) -> np.ndarray:
        """Generate volume series based on profile.

        Args:
            rng: Random number generator.
            n_bars: Number of bars.
            vol_profile: Volume profile type.

        Returns:
            Array of volume values.
        """
        base_volume = 10000.0

        # Generate base volume with variability
        volume = rng.lognormal(np.log(base_volume), 0.4, n_bars)

        # Apply profile pattern
        if vol_profile == "u_shape":
            # Higher volume at open and close
            time_factor = np.linspace(0, 1, n_bars)
            u_shape = 1 + 0.5 * (time_factor**2 + (1 - time_factor) ** 2)
            volume *= u_shape

        elif vol_profile == "morning_spike":
            # High volume in first hour, then decay
            decay = np.exp(-np.arange(n_bars) / (n_bars * 0.2))
            volume *= (1 + 0.8 * decay)

        elif vol_profile == "flat":
            # Uniform volume
            pass

        return volume

    def fetch_intraday(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> pd.DataFrame:
        """Fetch synthetic data (compatibility method).

        Args:
            symbol: Symbol identifier (can encode regime, e.g., 'SYN_TREND_UP').
            start: Start datetime.
            end: End datetime.
            interval: Interval (only '1m' supported).

        Returns:
            DataFrame with synthetic data.
        """
        if interval != "1m":
            raise ValueError(f"Synthetic provider only supports '1m' interval, got {interval}")

        # Parse symbol for regime hint
        regime = "choppy"
        if "TREND_UP" in symbol.upper() or "BULL" in symbol.upper():
            regime = "trend_up"
        elif "TREND_DOWN" in symbol.upper() or "BEAR" in symbol.upper():
            regime = "trend_down"
        elif "MEAN" in symbol.upper():
            regime = "mean_revert"

        # Calculate minutes
        minutes = int((end - start).total_seconds() / 60)

        # Generate deterministic seed from symbol and start time
        seed = hash(f"{symbol}_{start.isoformat()}") % (2**32)

        return self.generate_synthetic_day(
            seed=seed,
            regime=regime,
            minutes=minutes,
        )