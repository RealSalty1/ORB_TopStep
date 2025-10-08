"""Tests for data source providers."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from orb_confluence.data.sources.yahoo import YahooProvider
from orb_confluence.data.sources.binance import BinanceProvider
from orb_confluence.data.sources.synthetic import SyntheticProvider


class TestYahooProvider:
    """Test Yahoo Finance data provider."""

    def test_init(self):
        """Test provider initialization."""
        provider = YahooProvider(max_retries=5, rate_limit_delay=1.0)
        assert provider.name == "yahoo"
        assert provider.max_retries == 5
        assert provider.rate_limit_delay == 1.0

    def test_empty_dataframe_schema(self):
        """Test empty DataFrame has correct schema."""
        provider = YahooProvider()
        df = provider._empty_dataframe()

        expected_columns = [
            "timestamp_utc",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "source",
        ]
        assert list(df.columns) == expected_columns
        assert len(df) == 0

    @patch("orb_confluence.data.sources.yahoo.yf.Ticker")
    def test_fetch_success(self, mock_ticker):
        """Test successful data fetch."""
        # Create mock response
        mock_data = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [101.0, 102.0, 103.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.5, 101.5, 102.5],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=pd.DatetimeIndex(
                [
                    datetime(2024, 1, 2, 14, 30),
                    datetime(2024, 1, 2, 14, 31),
                    datetime(2024, 1, 2, 14, 32),
                ],
                name="Datetime",
                tz="US/Eastern",
            ),
        )

        mock_ticker.return_value.history.return_value = mock_data

        provider = YahooProvider()
        start = datetime(2024, 1, 2, 14, 30, tzinfo=None)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=None)

        df = provider.fetch_intraday("SPY", start, end, interval="1m")

        # Check schema
        assert "timestamp_utc" in df.columns
        assert "symbol" in df.columns
        assert df["symbol"].iloc[0] == "SPY"
        assert df["source"].iloc[0] == "yahoo"

        # Check data
        assert len(df) == 3
        assert df["close"].iloc[0] == 100.5

    @patch("orb_confluence.data.sources.yahoo.yf.Ticker")
    def test_fetch_empty_response(self, mock_ticker):
        """Test handling of empty response."""
        mock_ticker.return_value.history.return_value = pd.DataFrame()

        provider = YahooProvider()
        start = datetime(2024, 1, 2, 14, 30, tzinfo=None)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=None)

        df = provider.fetch_intraday("SPY", start, end, interval="1m")

        assert df.empty
        assert "timestamp_utc" in df.columns

    def test_invalid_interval(self):
        """Test that invalid interval raises error."""
        provider = YahooProvider()
        start = datetime(2024, 1, 2, 14, 30, tzinfo=None)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=None)

        with pytest.raises(ValueError, match="Unsupported interval"):
            provider.fetch_intraday("SPY", start, end, interval="3m")

    @patch("orb_confluence.data.sources.yahoo.yf.Ticker")
    def test_retry_logic(self, mock_ticker):
        """Test retry logic with exponential backoff."""
        # Fail twice, then succeed
        mock_ticker.return_value.history.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            pd.DataFrame(
                {
                    "Open": [100.0],
                    "High": [101.0],
                    "Low": [99.0],
                    "Close": [100.5],
                    "Volume": [1000000],
                },
                index=pd.DatetimeIndex(
                    [datetime(2024, 1, 2, 14, 30)], name="Datetime", tz="US/Eastern"
                ),
            ),
        ]

        provider = YahooProvider(max_retries=3)
        start = datetime(2024, 1, 2, 14, 30, tzinfo=None)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=None)

        df = provider.fetch_intraday("SPY", start, end, interval="1m")

        assert len(df) == 1
        assert mock_ticker.return_value.history.call_count == 3


class TestBinanceProvider:
    """Test Binance data provider."""

    def test_init(self):
        """Test provider initialization."""
        provider = BinanceProvider(max_retries=5, rate_limit_delay=0.5)
        assert provider.name == "binance"
        assert provider.max_retries == 5
        assert provider.rate_limit_delay == 0.5

    def test_empty_dataframe_schema(self):
        """Test empty DataFrame has correct schema."""
        provider = BinanceProvider()
        df = provider._empty_dataframe()

        expected_columns = [
            "timestamp_utc",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "source",
        ]
        assert list(df.columns) == expected_columns
        assert len(df) == 0

    @patch("orb_confluence.data.sources.binance.requests.get")
    def test_fetch_success(self, mock_get):
        """Test successful data fetch from Binance."""
        # Mock Binance kline response
        mock_response = Mock()
        mock_response.json.return_value = [
            [
                1704196200000,  # Open time
                "40000.00",  # Open
                "40100.00",  # High
                "39900.00",  # Low
                "40050.00",  # Close
                "10.5",  # Volume
                1704196259999,  # Close time
                "420525.00",  # Quote volume
                100,  # Trades
                "5.2",  # Taker buy base
                "208260.00",  # Taker buy quote
                "0",  # Ignore
            ],
            [
                1704196260000,
                "40050.00",
                "40150.00",
                "40000.00",
                "40100.00",
                "11.2",
                1704196319999,
                "449120.00",
                110,
                "5.6",
                "224560.00",
                "0",
            ],
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = BinanceProvider(rate_limit_delay=0.0)  # No delay for tests
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        df = provider.fetch_intraday("BTCUSDT", start, end, interval="1m")

        # Check schema
        assert "timestamp_utc" in df.columns
        assert "symbol" in df.columns
        assert df["symbol"].iloc[0] == "BTCUSDT"
        assert df["source"].iloc[0] == "binance"

        # Check data
        assert len(df) == 2
        assert df["close"].iloc[0] == 40050.00

    def test_invalid_interval(self):
        """Test that invalid interval raises error."""
        provider = BinanceProvider()
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        with pytest.raises(ValueError, match="Unsupported interval"):
            provider.fetch_intraday("BTCUSDT", start, end, interval="3m")

    @patch("orb_confluence.data.sources.binance.requests.get")
    def test_empty_response(self, mock_get):
        """Test handling of empty response."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        provider = BinanceProvider(rate_limit_delay=0.0)
        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        df = provider.fetch_intraday("BTCUSDT", start, end, interval="1m")

        assert df.empty


class TestSyntheticProvider:
    """Test synthetic data provider."""

    def test_init(self):
        """Test provider initialization."""
        provider = SyntheticProvider()
        assert provider.name == "synthetic"

    def test_reproducibility(self):
        """Test that same seed produces identical data."""
        provider = SyntheticProvider()

        df1 = provider.generate_synthetic_day(seed=42, regime="trend_up", minutes=390)
        df2 = provider.generate_synthetic_day(seed=42, regime="trend_up", minutes=390)

        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seeds(self):
        """Test that different seeds produce different data."""
        provider = SyntheticProvider()

        df1 = provider.generate_synthetic_day(seed=42, regime="trend_up")
        df2 = provider.generate_synthetic_day(seed=99, regime="trend_up")

        assert not df1["close"].equals(df2["close"])

    def test_schema(self):
        """Test output schema."""
        provider = SyntheticProvider()
        df = provider.generate_synthetic_day(seed=42, minutes=100)

        expected_columns = [
            "timestamp_utc",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "source",
        ]
        assert list(df.columns) == expected_columns
        assert len(df) == 100

    def test_ohlc_validity(self):
        """Test that generated OHLC is valid."""
        provider = SyntheticProvider()
        df = provider.generate_synthetic_day(seed=42, minutes=390)

        # Check: high >= low, high >= open, high >= close, low <= open, low <= close
        assert (df["high"] >= df["low"]).all()
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["open"]).all()
        assert (df["low"] <= df["close"]).all()

    def test_all_regimes(self):
        """Test all regime types."""
        provider = SyntheticProvider()

        regimes = ["trend_up", "trend_down", "mean_revert", "choppy"]

        for regime in regimes:
            df = provider.generate_synthetic_day(seed=42, regime=regime, minutes=100)
            assert len(df) == 100
            assert df["symbol"].iloc[0] == f"SYN_{regime.upper()}"

    def test_volatility_scaling(self):
        """Test volatility multiplier effect."""
        provider = SyntheticProvider()

        df_low_vol = provider.generate_synthetic_day(
            seed=42, regime="choppy", volatility_mult=0.3
        )
        df_high_vol = provider.generate_synthetic_day(
            seed=42, regime="choppy", volatility_mult=2.5
        )

        # High volatility should have larger price swings
        low_vol_range = df_low_vol["high"].max() - df_low_vol["low"].min()
        high_vol_range = df_high_vol["high"].max() - df_high_vol["low"].min()

        assert high_vol_range > low_vol_range

    def test_volume_profiles(self):
        """Test different volume profiles."""
        provider = SyntheticProvider()

        profiles = ["u_shape", "flat", "morning_spike"]

        for profile in profiles:
            df = provider.generate_synthetic_day(
                seed=42, minutes=100, vol_profile=profile
            )
            assert len(df) == 100
            assert (df["volume"] > 0).all()

    def test_fetch_intraday_compatibility(self):
        """Test fetch_intraday compatibility method."""
        provider = SyntheticProvider()

        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        df = provider.fetch_intraday("SYN_TREND_UP", start, end, interval="1m")

        assert len(df) == 30  # 30 minutes
        assert "timestamp_utc" in df.columns

    def test_fetch_intraday_invalid_interval(self):
        """Test that non-1m intervals raise error."""
        provider = SyntheticProvider()

        start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo)

        with pytest.raises(ValueError, match="only supports '1m'"):
            provider.fetch_intraday("SYN_TEST", start, end, interval="5m")
