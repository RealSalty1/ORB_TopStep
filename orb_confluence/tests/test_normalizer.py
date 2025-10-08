"""Tests for data normalizer."""

from datetime import datetime, time

import pandas as pd
import pytest

from orb_confluence.data.normalizer import normalize_bars, filter_to_session


class TestNormalizer:
    """Test data normalization."""

    def test_basic_normalization(self):
        """Test basic normalization without session filtering."""
        df = pd.DataFrame(
            {
                "timestamp_utc": [
                    datetime(2024, 1, 2, 14, 35, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 32, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 33, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                ],
                "open": ["100.0", "99.5", "100.5"],
                "high": ["101.0", "100.0", "101.5"],
                "low": ["99.0", "99.0", "100.0"],
                "close": ["100.5", "100.0", "101.0"],
                "volume": ["1000", "1100", "1200"],
            }
        )

        result = normalize_bars(df)

        # Check sorted
        assert result["timestamp_utc"].is_monotonic_increasing

        # Check types
        assert pd.api.types.is_float_dtype(result["open"])
        assert pd.api.types.is_float_dtype(result["volume"])

        # Check length
        assert len(result) == 3

    def test_duplicate_removal(self):
        """Test duplicate timestamp removal."""
        df = pd.DataFrame(
            {
                "timestamp_utc": [
                    datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 31, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # Duplicate
                ],
                "open": [100.0, 101.0, 100.1],
                "high": [101.0, 102.0, 101.1],
                "low": [99.0, 100.0, 99.1],
                "close": [100.5, 101.5, 100.6],
                "volume": [1000, 1100, 1050],
            }
        )

        result = normalize_bars(df)

        # Should keep first occurrence
        assert len(result) == 2
        assert result["close"].iloc[0] == 100.5  # First 14:30 bar

    def test_missing_column(self):
        """Test that missing required column raises error."""
        df = pd.DataFrame(
            {
                "timestamp_utc": [datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo)],
                "open": [100.0],
                # Missing high, low, close, volume
            }
        )

        with pytest.raises(ValueError, match="Missing required column"):
            normalize_bars(df)

    def test_session_filtering(self):
        """Test session filtering."""
        # Create data spanning full day
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 13, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # 8:00 ET
                    end=datetime(2024, 1, 2, 22, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # 17:00 ET
                    freq="1h",
                ),
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.5] * 10,
                "volume": [1000] * 10,
            }
        )

        # Filter to RTH (9:30-16:00 ET)
        result = normalize_bars(
            df,
            session_start=time(9, 30),
            session_end=time(16, 0),
            timezone_name="America/New_York",
        )

        # Should filter to session hours
        assert len(result) < len(df)

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame(
            columns=["timestamp_utc", "open", "high", "low", "close", "volume"]
        )

        result = normalize_bars(df)

        assert result.empty
        assert "timestamp_utc" in result.columns


class TestSessionFilter:
    """Test session filtering."""

    def test_filter_to_rth(self):
        """Test filtering to regular trading hours."""
        # Create minute bars from 8:00 to 18:00 ET
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 13, 0, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # 8:00 ET
                    periods=600,  # 10 hours
                    freq="1min",
                ),
                "open": [100.0] * 600,
                "high": [101.0] * 600,
                "low": [99.0] * 600,
                "close": [100.5] * 600,
                "volume": [1000] * 600,
            }
        )

        # Filter to 9:30-16:00 ET (RTH)
        result = filter_to_session(
            df,
            session_start=time(9, 30),
            session_end=time(16, 0),
            timezone_name="America/New_York",
        )

        # 9:30-16:00 = 6.5 hours = 390 minutes
        assert len(result) == 390

    def test_empty_dataframe(self):
        """Test filtering empty DataFrame."""
        df = pd.DataFrame(columns=["timestamp_utc"])

        result = filter_to_session(
            df,
            session_start=time(9, 30),
            session_end=time(16, 0),
        )

        assert result.empty
