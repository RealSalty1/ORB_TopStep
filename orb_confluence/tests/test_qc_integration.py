"""Tests for QC integration: validate_or_window and detect_outliers."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.data.qc import validate_or_window, detect_outliers


class TestValidateORWindow:
    """Tests for validate_or_window function."""
    
    def test_valid_continuous_window(self):
        """Test validation passes for continuous minute coverage."""
        # Generate 15 continuous minutes
        start = datetime(2024, 1, 2, 9, 30)
        timestamps = [start + timedelta(minutes=i) for i in range(15)]
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100 + i * 0.1 for i in range(15)],
            'low': [99 + i * 0.1 for i in range(15)],
            'open': [99.5 + i * 0.1 for i in range(15)],
            'close': [100 + i * 0.1 for i in range(15)],
        })
        
        assert validate_or_window(bars, or_duration_minutes=15) is True
    
    def test_missing_minute_fails(self):
        """Test validation fails when minute is missing."""
        # Generate 15 minutes but skip minute 5
        start = datetime(2024, 1, 2, 9, 30)
        timestamps = [start + timedelta(minutes=i) for i in range(15) if i != 5]
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100 + i * 0.1 for i in range(14)],
            'low': [99 + i * 0.1 for i in range(14)],
            'open': [99.5 + i * 0.1 for i in range(14)],
            'close': [100 + i * 0.1 for i in range(14)],
        })
        
        # Should fail due to gap
        assert validate_or_window(bars, or_duration_minutes=15) is False
    
    def test_insufficient_bars_fails(self):
        """Test validation fails with insufficient bars."""
        # Only 10 bars for 15-minute OR
        start = datetime(2024, 1, 2, 9, 30)
        timestamps = [start + timedelta(minutes=i) for i in range(10)]
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100] * 10,
            'low': [99] * 10,
            'open': [99.5] * 10,
            'close': [100] * 10,
        })
        
        assert validate_or_window(bars, or_duration_minutes=15) is False
    
    def test_invalid_ohlc_fails(self):
        """Test validation fails with invalid OHLC."""
        start = datetime(2024, 1, 2, 9, 30)
        timestamps = [start + timedelta(minutes=i) for i in range(15)]
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100] * 15,
            'low': [101] * 15,  # Low > High (invalid!)
            'open': [99.5] * 15,
            'close': [100] * 15,
        })
        
        assert validate_or_window(bars, or_duration_minutes=15) is False
    
    def test_empty_dataframe_fails(self):
        """Test validation fails for empty DataFrame."""
        bars = pd.DataFrame()
        assert validate_or_window(bars, or_duration_minutes=15) is False
    
    def test_datetimeindex_supported(self):
        """Test validation works with DatetimeIndex."""
        start = datetime(2024, 1, 2, 9, 30)
        timestamps = pd.date_range(start, periods=15, freq='1min')
        
        bars = pd.DataFrame({
            'high': [100 + i * 0.1 for i in range(15)],
            'low': [99 + i * 0.1 for i in range(15)],
            'open': [99.5 + i * 0.1 for i in range(15)],
            'close': [100 + i * 0.1 for i in range(15)],
        }, index=timestamps)
        
        assert validate_or_window(bars, or_duration_minutes=15) is True


class TestDetectOutliers:
    """Tests for detect_outliers function."""
    
    def test_iqr_method_no_outliers(self):
        """Test IQR method with no outliers."""
        volume = pd.Series([100, 105, 95, 110, 90, 100, 105])
        outliers = detect_outliers(volume, method='iqr', threshold=3.0)
        assert len(outliers) == 0
    
    def test_iqr_method_with_outliers(self):
        """Test IQR method detects outliers."""
        volume = pd.Series([100, 105, 95, 110, 90, 100, 500])  # 500 is outlier
        outliers = detect_outliers(volume, method='iqr', threshold=1.5)
        assert len(outliers) > 0
        assert 6 in outliers  # Index of 500
    
    def test_zscore_method(self):
        """Test z-score method."""
        volume = pd.Series([100, 105, 95, 110, 90, 100, 500])
        outliers = detect_outliers(volume, method='zscore', threshold=2.0)
        assert len(outliers) > 0
        assert 6 in outliers
    
    def test_mad_method(self):
        """Test MAD (Median Absolute Deviation) method."""
        volume = pd.Series([100, 105, 95, 110, 90, 100, 500])
        outliers = detect_outliers(volume, method='mad', threshold=3.0)
        assert len(outliers) > 0
        assert 6 in outliers
    
    def test_empty_series(self):
        """Test with empty series."""
        volume = pd.Series([])
        outliers = detect_outliers(volume, method='iqr')
        assert len(outliers) == 0
    
    def test_all_same_values(self):
        """Test with all same values (no variation)."""
        volume = pd.Series([100] * 10)
        outliers = detect_outliers(volume, method='zscore')
        assert len(outliers) == 0
    
    def test_invalid_method_raises(self):
        """Test invalid method raises error."""
        volume = pd.Series([100, 105, 95])
        with pytest.raises(ValueError, match="Unknown method"):
            detect_outliers(volume, method='invalid')
    
    def test_outlier_on_both_ends(self):
        """Test detection of outliers on both high and low ends."""
        volume = pd.Series([5, 100, 105, 95, 110, 90, 500])
        outliers = detect_outliers(volume, method='iqr', threshold=1.5)
        assert len(outliers) >= 2  # Should catch both 5 and 500


class TestORWindowIntegration:
    """Integration tests for OR window validation."""
    
    def test_inject_missing_minute_scenario(self):
        """Test scenario where missing minute is injected (simulated data issue)."""
        # Generate bars but intentionally skip one minute
        start = datetime(2024, 1, 2, 9, 30)
        minutes = list(range(15))
        minutes.remove(7)  # Remove minute 7 (simulate gap)
        
        timestamps = [start + timedelta(minutes=i) for i in minutes]
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100.0] * len(timestamps),
            'low': [99.0] * len(timestamps),
            'open': [99.5] * len(timestamps),
            'close': [100.0] * len(timestamps),
        })
        
        # Should fail validation
        is_valid = validate_or_window(bars, or_duration_minutes=15)
        assert is_valid is False
        
        # Now "inject" the missing minute (fix the data)
        missing_bar = pd.DataFrame({
            'timestamp_utc': [start + timedelta(minutes=7)],
            'high': [100.0],
            'low': [99.0],
            'open': [99.5],
            'close': [100.0],
        })
        
        bars_fixed = pd.concat([bars, missing_bar]).sort_values('timestamp_utc').reset_index(drop=True)
        
        # Should now pass
        is_valid_fixed = validate_or_window(bars_fixed, or_duration_minutes=15)
        assert is_valid_fixed is True
    
    def test_large_gap_detection(self):
        """Test detection of large gap (e.g., 5-minute gap)."""
        start = datetime(2024, 1, 2, 9, 30)
        
        # First 5 minutes continuous
        first_segment = [start + timedelta(minutes=i) for i in range(5)]
        
        # Gap of 5 minutes
        
        # Last 10 minutes continuous
        second_segment = [start + timedelta(minutes=i) for i in range(10, 20)]
        
        timestamps = first_segment + second_segment
        
        bars = pd.DataFrame({
            'timestamp_utc': timestamps,
            'high': [100.0] * len(timestamps),
            'low': [99.0] * len(timestamps),
            'open': [99.5] * len(timestamps),
            'close': [100.0] * len(timestamps),
        })
        
        # Should fail due to gap
        is_valid = validate_or_window(bars, or_duration_minutes=15)
        assert is_valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
