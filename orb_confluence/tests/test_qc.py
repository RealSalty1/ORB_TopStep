"""Tests for data quality control."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.data.qc import (
    DayQualityReport,
    quality_check,
    detect_gaps,
    check_or_window,
    check_ohlc_validity,
)


class TestQualityCheck:
    """Test quality check functionality."""

    def test_perfect_day(self):
        """Test quality check on perfect data."""
        # Generate 390 consecutive minute bars (full trading day)
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    periods=390,
                    freq="1min",
                ),
                "open": [100.0] * 390,
                "high": [101.0] * 390,
                "low": [99.0] * 390,
                "close": [100.5] * 390,
                "volume": [1000] * 390,
            }
        )

        report = quality_check(df, or_duration_minutes=15, expected_bars_per_day=390)

        assert report.passed is True
        assert report.total_bars == 390
        assert report.missing_bars == 0
        assert report.duplicate_timestamps == 0
        assert len(report.gaps) == 0
        assert report.or_window_complete is True
        assert report.invalid_ohlc_count == 0

    def test_missing_bars(self):
        """Test detection of missing bars."""
        # Generate data with gaps
        timestamps = list(
            pd.date_range(
                start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                periods=100,
                freq="1min",
            )
        )

        # Add gap (skip 10 bars)
        timestamps.extend(
            pd.date_range(
                start=datetime(2024, 1, 2, 16, 20, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                periods=100,
                freq="1min",
            )
        )

        df = pd.DataFrame(
            {
                "timestamp_utc": timestamps,
                "open": [100.0] * 200,
                "high": [101.0] * 200,
                "low": [99.0] * 200,
                "close": [100.5] * 200,
                "volume": [1000] * 200,
            }
        )

        report = quality_check(df, expected_bars_per_day=390)

        assert report.total_bars == 200
        assert report.missing_bars == 190
        assert len(report.gaps) > 0

    def test_incomplete_or_window(self):
        """Test detection of incomplete OR window."""
        # Generate data starting late (OR incomplete)
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 14, 45, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # Starts at minute 15
                    periods=375,
                    freq="1min",
                ),
                "open": [100.0] * 375,
                "high": [101.0] * 375,
                "low": [99.0] * 375,
                "close": [100.5] * 375,
                "volume": [1000] * 375,
            }
        )

        report = quality_check(df, or_duration_minutes=15)

        assert report.or_window_complete is False
        assert "Incomplete OR window" in str(report.failure_reasons)

    def test_invalid_ohlc(self):
        """Test detection of invalid OHLC relationships."""
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    periods=10,
                    freq="1min",
                ),
                "open": [100.0] * 10,
                "high": [99.0] * 10,  # Invalid: high < open
                "low": [98.0] * 10,
                "close": [100.5] * 10,
                "volume": [1000] * 10,
            }
        )

        report = quality_check(df, expected_bars_per_day=10)

        assert report.invalid_ohlc_count > 0
        assert "invalid OHLC" in str(report.failure_reasons)

    def test_zero_volume(self):
        """Test detection of zero volume bars."""
        df = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(
                    start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    periods=10,
                    freq="1min",
                ),
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.5] * 10,
                "volume": [0] * 10,  # Zero volume
            }
        )

        report = quality_check(df, expected_bars_per_day=10)

        assert report.zero_volume_count == 10
        assert "zero-volume" in str(report.failure_reasons)

    def test_duplicate_timestamps(self):
        """Test detection of duplicate timestamps."""
        df = pd.DataFrame(
            {
                "timestamp_utc": [
                    datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 31, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                    datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),  # Duplicate
                    datetime(2024, 1, 2, 14, 32, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                ],
                "open": [100.0, 101.0, 100.1, 102.0],
                "high": [101.0, 102.0, 101.1, 103.0],
                "low": [99.0, 100.0, 99.1, 101.0],
                "close": [100.5, 101.5, 100.6, 102.5],
                "volume": [1000, 1100, 1050, 1200],
            }
        )

        report = quality_check(df, expected_bars_per_day=4)

        assert report.duplicate_timestamps > 0

    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame(columns=["timestamp_utc", "open", "high", "low", "close", "volume"])

        report = quality_check(df)

        assert report.passed is False
        assert report.total_bars == 0


class TestGapDetection:
    """Test gap detection."""

    def test_no_gaps(self):
        """Test continuous data with no gaps."""
        timestamps = pd.Series(
            pd.date_range(
                start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                periods=100,
                freq="1min",
            )
        )

        gaps = detect_gaps(timestamps)

        assert len(gaps) == 0

    def test_single_gap(self):
        """Test detection of single gap."""
        timestamps1 = pd.date_range(
            start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            periods=50,
            freq="1min",
        )

        # 10-minute gap
        timestamps2 = pd.date_range(
            start=datetime(2024, 1, 2, 15, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            periods=50,
            freq="1min",
        )

        timestamps = pd.Series(list(timestamps1) + list(timestamps2))

        gaps = detect_gaps(timestamps)

        assert len(gaps) == 1
        assert (gaps[0][1] - gaps[0][0]) > pd.Timedelta("1min")

    def test_multiple_gaps(self):
        """Test detection of multiple gaps."""
        timestamps = []

        # Add 3 blocks with gaps between
        for i in range(3):
            start = datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo) + timedelta(
                minutes=i * 100
            )
            block = pd.date_range(start=start, periods=20, freq="1min")
            timestamps.extend(block)

        timestamps = pd.Series(timestamps)

        gaps = detect_gaps(timestamps)

        assert len(gaps) == 2


class TestORWindowCheck:
    """Test OR window completeness check."""

    def test_complete_or_window(self):
        """Test complete OR window."""
        timestamps = pd.Series(
            pd.date_range(
                start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                periods=390,
                freq="1min",
            )
        )

        is_complete, gaps = check_or_window(timestamps, or_duration_minutes=15)

        assert is_complete is True
        assert len(gaps) == 0

    def test_incomplete_or_window(self):
        """Test incomplete OR window."""
        # Start at minute 10 (missing first 10 minutes)
        timestamps = pd.Series(
            pd.date_range(
                start=datetime(2024, 1, 2, 14, 40, tzinfo=pd.Timestamp.now("UTC").tzinfo),
                periods=380,
                freq="1min",
            )
        )

        is_complete, gaps = check_or_window(timestamps, or_duration_minutes=15)

        assert is_complete is False

    def test_or_window_with_gap(self):
        """Test OR window with gap."""
        timestamps1 = pd.date_range(
            start=datetime(2024, 1, 2, 14, 30, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            periods=5,
            freq="1min",
        )

        # Gap
        timestamps2 = pd.date_range(
            start=datetime(2024, 1, 2, 14, 38, tzinfo=pd.Timestamp.now("UTC").tzinfo),
            periods=400,
            freq="1min",
        )

        timestamps = pd.Series(list(timestamps1) + list(timestamps2))

        is_complete, gaps = check_or_window(timestamps, or_duration_minutes=15)

        assert is_complete is False
        assert len(gaps) > 0


class TestOHLCValidity:
    """Test OHLC validity check."""

    def test_valid_ohlc(self):
        """Test valid OHLC relationships."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.0],
            }
        )

        invalid_count = check_ohlc_validity(df)

        assert invalid_count == 0

    def test_high_less_than_low(self):
        """Test invalid: high < low."""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [99.0],  # Invalid
                "low": [101.0],
                "close": [100.5],
            }
        )

        invalid_count = check_ohlc_validity(df)

        assert invalid_count == 1

    def test_high_less_than_close(self):
        """Test invalid: high < close."""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [102.0],  # Invalid: > high
            }
        )

        invalid_count = check_ohlc_validity(df)

        assert invalid_count == 1

    def test_low_greater_than_open(self):
        """Test invalid: low > open."""
        df = pd.DataFrame(
            {
                "open": [100.0],
                "high": [102.0],
                "low": [101.0],  # Invalid: > open
                "close": [101.5],
            }
        )

        invalid_count = check_ohlc_validity(df)

        assert invalid_count == 1
