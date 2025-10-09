"""Unit tests for advanced features module."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

from orb_confluence.features.advanced_features import AdvancedFeatures


@pytest.fixture
def features():
    """Create AdvancedFeatures instance."""
    return AdvancedFeatures()


@pytest.fixture
def sample_bars_1m():
    """Create sample 1-minute bars for testing."""
    n_bars = 390  # Full trading day
    start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
    
    timestamps = [start_time + timedelta(minutes=i) for i in range(n_bars)]
    
    # Generate realistic price action
    base_price = 5800.0
    prices = base_price + np.cumsum(np.random.randn(n_bars) * 0.5)
    
    bars = pd.DataFrame({
        'timestamp_utc': timestamps,
        'open': prices + np.random.randn(n_bars) * 0.25,
        'high': prices + abs(np.random.randn(n_bars)) * 0.5,
        'low': prices - abs(np.random.randn(n_bars)) * 0.5,
        'close': prices + np.random.randn(n_bars) * 0.25,
        'volume': np.random.randint(50, 500, n_bars),
    })
    
    # Ensure high >= open, close and low <= open, close
    bars['high'] = bars[['high', 'open', 'close']].max(axis=1)
    bars['low'] = bars[['low', 'open', 'close']].min(axis=1)
    
    return bars


@pytest.fixture
def sample_bars_daily():
    """Create sample daily bars for testing."""
    n_bars = 60  # 2-3 months
    start_date = pd.Timestamp("2024-11-01", tz='UTC')
    
    dates = [start_date + timedelta(days=i) for i in range(n_bars)]
    
    base_price = 5800.0
    prices = base_price + np.cumsum(np.random.randn(n_bars) * 10)
    
    bars = pd.DataFrame({
        'timestamp_utc': dates,
        'open': prices + np.random.randn(n_bars) * 5,
        'high': prices + abs(np.random.randn(n_bars)) * 15,
        'low': prices - abs(np.random.randn(n_bars)) * 15,
        'close': prices + np.random.randn(n_bars) * 5,
        'volume': np.random.randint(50000, 500000, n_bars),
    })
    
    bars['high'] = bars[['high', 'open', 'close']].max(axis=1)
    bars['low'] = bars[['low', 'open', 'close']].min(axis=1)
    
    return bars


@pytest.fixture
def sample_bars_1s():
    """Create sample 1-second bars for testing."""
    n_bars = 600  # 10 minutes
    start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
    
    timestamps = [start_time + timedelta(seconds=i) for i in range(n_bars)]
    
    base_price = 5800.0
    prices = base_price + np.cumsum(np.random.randn(n_bars) * 0.05)
    
    bars = pd.DataFrame({
        'timestamp_utc': timestamps,
        'open': prices + np.random.randn(n_bars) * 0.1,
        'high': prices + abs(np.random.randn(n_bars)) * 0.15,
        'low': prices - abs(np.random.randn(n_bars)) * 0.15,
        'close': prices + np.random.randn(n_bars) * 0.1,
        'volume': np.random.randint(1, 50, n_bars),
    })
    
    bars['high'] = bars[['high', 'open', 'close']].max(axis=1)
    bars['low'] = bars[['low', 'open', 'close']].min(axis=1)
    
    return bars


class TestVolatilityTermStructure:
    """Tests for volatility_term_structure feature."""
    
    def test_basic_calculation(self, features, sample_bars_1m, sample_bars_daily):
        """Test basic VTS calculation."""
        vts = features.volatility_term_structure(sample_bars_1m, sample_bars_daily)
        
        assert isinstance(vts, float)
        assert vts > 0
        assert vts < 10  # Reasonable range
    
    def test_high_intraday_volatility(self, features, sample_bars_daily):
        """Test VTS with elevated intraday volatility."""
        # Create high volatility 1m bars
        n_bars = 100
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        high_vol_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.random.randn(n_bars) * 10,  # High volatility
            'high': 5810 + np.random.randn(n_bars) * 10,
            'low': 5790 + np.random.randn(n_bars) * 10,
            'close': 5800 + np.random.randn(n_bars) * 10,
            'volume': np.random.randint(50, 500, n_bars),
        })
        
        high_vol_bars['high'] = high_vol_bars[['high', 'open', 'close']].max(axis=1)
        high_vol_bars['low'] = high_vol_bars[['low', 'open', 'close']].min(axis=1)
        
        vts = features.volatility_term_structure(high_vol_bars, sample_bars_daily)
        
        # Should be elevated
        assert vts > 0.5
    
    def test_handles_zero_daily_atr(self, features, sample_bars_1m):
        """Test handling of zero daily ATR."""
        # Create flat daily bars
        flat_daily = pd.DataFrame({
            'timestamp_utc': pd.date_range(start="2024-11-01", periods=30, tz='UTC'),
            'open': [5800] * 30,
            'high': [5800] * 30,
            'low': [5800] * 30,
            'close': [5800] * 30,
            'volume': [100000] * 30,
        })
        
        vts = features.volatility_term_structure(sample_bars_1m, flat_daily)
        
        # Should return neutral value
        assert vts == 1.0


class TestOvernightAuctionImbalance:
    """Tests for overnight_auction_imbalance feature."""
    
    def test_basic_calculation(self, features):
        """Test basic overnight imbalance calculation."""
        # Create overnight bars with clear imbalance
        n_bars = 30
        start_time = pd.Timestamp("2025-01-15 00:00:00", tz='UTC')
        
        overnight_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i*15) for i in range(n_bars)],
            'open': 5800 + np.random.randn(n_bars) * 2,
            'high': 5805 + np.random.randn(n_bars) * 2,
            'low': 5795 + np.random.randn(n_bars) * 2,
            'close': 5800 + np.random.randn(n_bars) * 2,
            'volume': [100 if i < 10 else 500 for i in range(n_bars)],  # Imbalanced volume
        })
        
        overnight_bars['high'] = overnight_bars[['high', 'open', 'close']].max(axis=1)
        overnight_bars['low'] = overnight_bars[['low', 'open', 'close']].min(axis=1)
        
        imbalance = features.overnight_auction_imbalance(overnight_bars)
        
        assert isinstance(imbalance, float)
        assert 0 <= imbalance <= 1
    
    def test_insufficient_bars(self, features):
        """Test with insufficient bars."""
        short_bars = pd.DataFrame({
            'timestamp_utc': [pd.Timestamp("2025-01-15", tz='UTC')],
            'open': [5800],
            'high': [5810],
            'low': [5790],
            'close': [5800],
            'volume': [100],
        })
        
        imbalance = features.overnight_auction_imbalance(short_bars)
        
        assert imbalance == 0.0
    
    def test_zero_range(self, features):
        """Test with zero overnight range."""
        flat_bars = pd.DataFrame({
            'timestamp_utc': pd.date_range(start="2025-01-15", periods=20, freq='15min', tz='UTC'),
            'open': [5800] * 20,
            'high': [5800] * 20,
            'low': [5800] * 20,
            'close': [5800] * 20,
            'volume': [100] * 20,
        })
        
        imbalance = features.overnight_auction_imbalance(flat_bars)
        
        assert imbalance == 0.0


class TestRotationEntropy:
    """Tests for rotation_entropy feature."""
    
    def test_high_entropy_choppy_market(self, features):
        """Test high entropy in choppy market."""
        # Create choppy bars (high rotation)
        n_bars = 100
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        choppy_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.sin(np.arange(n_bars) * 0.5) * 5,
            'high': 5810 + np.sin(np.arange(n_bars) * 0.5) * 5,
            'low': 5790 + np.sin(np.arange(n_bars) * 0.5) * 5,
            'close': 5800 + np.sin(np.arange(n_bars) * 0.5) * 5,
            'volume': [100] * n_bars,
        })
        
        # Make many rotation bars
        for i in range(1, n_bars, 2):
            choppy_bars.loc[i, 'high'] = choppy_bars.loc[i-1, 'high'] + 1
            choppy_bars.loc[i, 'low'] = choppy_bars.loc[i-1, 'low'] - 1
        
        entropy = features.rotation_entropy(choppy_bars)
        
        assert isinstance(entropy, float)
        assert 0 <= entropy <= 1
        assert entropy > 0.4  # Should be relatively high
    
    def test_low_entropy_trending_market(self, features):
        """Test low entropy in trending market."""
        # Create trending bars (low rotation)
        n_bars = 100
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        trending_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.arange(n_bars) * 0.5,  # Steady uptrend
            'high': 5810 + np.arange(n_bars) * 0.5,
            'low': 5795 + np.arange(n_bars) * 0.5,
            'close': 5805 + np.arange(n_bars) * 0.5,
            'volume': [100] * n_bars,
        })
        
        entropy = features.rotation_entropy(trending_bars)
        
        assert entropy < 0.6  # Should be lower for trending


class TestRelativeVolumeIntensity:
    """Tests for relative_volume_intensity feature."""
    
    def test_elevated_volume(self, features, sample_bars_daily):
        """Test with elevated current volume."""
        # Create high volume today
        n_bars = 60
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        high_vol_today = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.random.randn(n_bars) * 2,
            'high': 5810 + np.random.randn(n_bars) * 2,
            'low': 5790 + np.random.randn(n_bars) * 2,
            'close': 5800 + np.random.randn(n_bars) * 2,
            'volume': np.random.randint(800, 1200, n_bars),  # High volume
        })
        
        high_vol_today['high'] = high_vol_today[['high', 'open', 'close']].max(axis=1)
        high_vol_today['low'] = high_vol_today[['low', 'open', 'close']].min(axis=1)
        
        # Add date column to historical bars for grouping
        sample_bars_daily_with_minutes = pd.DataFrame()
        for idx, row in sample_bars_daily.iterrows():
            daily_bars = pd.DataFrame({
                'timestamp_utc': pd.date_range(
                    start=row['timestamp_utc'], 
                    periods=60, 
                    freq='1min'
                ),
                'open': row['open'] + np.random.randn(60) * 0.1,
                'high': row['high'] + np.random.randn(60) * 0.1,
                'low': row['low'] + np.random.randn(60) * 0.1,
                'close': row['close'] + np.random.randn(60) * 0.1,
                'volume': np.random.randint(50, 200, 60),  # Normal volume
            })
            sample_bars_daily_with_minutes = pd.concat([sample_bars_daily_with_minutes, daily_bars])
        
        intensity = features.relative_volume_intensity(
            high_vol_today, 
            sample_bars_daily_with_minutes
        )
        
        assert isinstance(intensity, float)
        # Should be elevated
        assert intensity > 0.0


class TestDirectionalCommitment:
    """Tests for directional_commitment feature."""
    
    def test_strong_directional_move(self, features):
        """Test with strong directional commitment."""
        n_bars = 60
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # All bullish bars
        directional_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.arange(n_bars) * 0.5,
            'high': 5810 + np.arange(n_bars) * 0.5,
            'low': 5795 + np.arange(n_bars) * 0.5,
            'close': 5805 + np.arange(n_bars) * 0.5,  # Always closes higher
            'volume': [100] * n_bars,
        })
        
        commitment = features.directional_commitment(directional_bars)
        
        assert isinstance(commitment, float)
        assert 0 <= commitment <= 1
        assert commitment > 0.7  # Strong directional commitment
    
    def test_mixed_bars(self, features):
        """Test with mixed directional bars."""
        n_bars = 60
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Alternating up and down bars
        closes = [5805 if i % 2 == 0 else 5795 for i in range(n_bars)]
        
        mixed_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': [5800] * n_bars,
            'high': [5810] * n_bars,
            'low': [5790] * n_bars,
            'close': closes,
            'volume': [100] * n_bars,
        })
        
        commitment = features.directional_commitment(mixed_bars)
        
        assert commitment < 0.5  # Low commitment due to back-and-forth


class TestMicrostructurePressure:
    """Tests for microstructure_pressure feature."""
    
    def test_buying_pressure(self, features):
        """Test with buying pressure."""
        n_bars = 300
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Mostly bullish 1s bars
        buying_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(seconds=i) for i in range(n_bars)],
            'open': 5800 + np.arange(n_bars) * 0.01,
            'high': 5801 + np.arange(n_bars) * 0.01,
            'low': 5799 + np.arange(n_bars) * 0.01,
            'close': 5801 + np.arange(n_bars) * 0.01,  # Closes > opens
            'volume': [10] * n_bars,
        })
        
        pressure = features.microstructure_pressure(buying_bars)
        
        assert isinstance(pressure, float)
        assert -1 <= pressure <= 1
        assert pressure > 0  # Buying pressure
    
    def test_balanced_pressure(self, features):
        """Test with balanced pressure."""
        n_bars = 300
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Equal up and down bars
        balanced_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(seconds=i) for i in range(n_bars)],
            'open': [5800] * n_bars,
            'high': [5801] * n_bars,
            'low': [5799] * n_bars,
            'close': [5801 if i % 2 == 0 else 5799 for i in range(n_bars)],
            'volume': [10] * n_bars,
        })
        
        pressure = features.microstructure_pressure(balanced_bars)
        
        assert abs(pressure) < 0.2  # Should be near zero


class TestIntradayYieldCurve:
    """Tests for intraday_yield_curve feature."""
    
    def test_efficient_path(self, features):
        """Test efficient directional path."""
        n_bars = 60
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Smooth trend with small bars
        efficient_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.arange(n_bars) * 0.5,
            'high': 5801 + np.arange(n_bars) * 0.5,  # Small ranges
            'low': 5799 + np.arange(n_bars) * 0.5,
            'close': 5800.5 + np.arange(n_bars) * 0.5,
            'volume': [100] * n_bars,
        })
        
        yield_curve = features.intraday_yield_curve(efficient_bars)
        
        assert isinstance(yield_curve, float)
        assert yield_curve > 0
        assert yield_curve < 15  # Efficient path
    
    def test_choppy_path(self, features):
        """Test inefficient choppy path."""
        n_bars = 60
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Large bar ranges but small overall range
        choppy_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(minutes=i) for i in range(n_bars)],
            'open': 5800 + np.sin(np.arange(n_bars) * 0.5) * 2,
            'high': 5810 + np.sin(np.arange(n_bars) * 0.5) * 2,  # Large bars
            'low': 5790 + np.sin(np.arange(n_bars) * 0.5) * 2,
            'close': 5800 + np.sin(np.arange(n_bars) * 0.5) * 2,
            'volume': [100] * n_bars,
        })
        
        yield_curve = features.intraday_yield_curve(choppy_bars)
        
        assert yield_curve > 15  # Inefficient path


class TestCompositeLiquidityScore:
    """Tests for composite_liquidity_score feature."""
    
    def test_high_liquidity(self, features):
        """Test with high liquidity conditions."""
        n_bars = 300
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Tight spreads, consistent volume
        liquid_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(seconds=i) for i in range(n_bars)],
            'open': 5800 + np.random.randn(n_bars) * 0.05,
            'high': 5800.1 + np.random.randn(n_bars) * 0.05,  # Tight spread
            'low': 5799.9 + np.random.randn(n_bars) * 0.05,
            'close': 5800 + np.random.randn(n_bars) * 0.05,
            'volume': np.random.randint(90, 110, n_bars),  # Consistent volume
        })
        
        liquid_bars['high'] = liquid_bars[['high', 'open', 'close']].max(axis=1)
        liquid_bars['low'] = liquid_bars[['low', 'open', 'close']].min(axis=1)
        
        liquidity = features.composite_liquidity_score(liquid_bars)
        
        assert isinstance(liquidity, float)
        assert 0 <= liquidity <= 1
        assert liquidity > 0.5  # Good liquidity
    
    def test_low_liquidity(self, features):
        """Test with poor liquidity conditions."""
        n_bars = 300
        start_time = pd.Timestamp("2025-01-15 09:30:00", tz='UTC')
        
        # Wide spreads, erratic volume, gaps
        illiquid_bars = pd.DataFrame({
            'timestamp_utc': [start_time + timedelta(seconds=i) for i in range(n_bars)],
            'open': 5800 + np.random.randn(n_bars) * 2,
            'high': 5810 + np.random.randn(n_bars) * 3,  # Wide spreads
            'low': 5790 + np.random.randn(n_bars) * 3,
            'close': 5800 + np.random.randn(n_bars) * 2,
            'volume': [0 if i % 3 == 0 else np.random.randint(10, 200) for i in range(n_bars)],  # Erratic
        })
        
        illiquid_bars['high'] = illiquid_bars[['high', 'open', 'close']].max(axis=1)
        illiquid_bars['low'] = illiquid_bars[['low', 'open', 'close']].min(axis=1)
        
        liquidity = features.composite_liquidity_score(illiquid_bars)
        
        assert liquidity < 0.7  # Poor liquidity


class TestCalculateAllFeatures:
    """Tests for calculate_all_features method."""
    
    def test_all_features_calculated(
        self, features, sample_bars_1m, sample_bars_daily, sample_bars_1s
    ):
        """Test that all features are calculated."""
        overnight_bars = sample_bars_1m.head(30)
        
        all_features = features.calculate_all_features(
            sample_bars_1m,
            sample_bars_daily,
            sample_bars_1s,
            overnight_bars
        )
        
        assert isinstance(all_features, dict)
        assert len(all_features) == 8
        
        expected_features = [
            'volatility_term_structure',
            'overnight_auction_imbalance',
            'rotation_entropy',
            'relative_volume_intensity',
            'directional_commitment',
            'microstructure_pressure',
            'intraday_yield_curve',
            'composite_liquidity_score',
        ]
        
        for feature_name in expected_features:
            assert feature_name in all_features
            assert isinstance(all_features[feature_name], float)
    
    def test_without_optional_data(self, features, sample_bars_1m, sample_bars_daily):
        """Test calculation without optional 1s and overnight data."""
        all_features = features.calculate_all_features(
            sample_bars_1m,
            sample_bars_daily,
            bars_1s=None,
            overnight_bars=None
        )
        
        assert len(all_features) == 8
        
        # Optional features should use approximations
        assert all_features['overnight_auction_imbalance'] == 0.0
        assert isinstance(all_features['microstructure_pressure'], float)
        assert isinstance(all_features['composite_liquidity_score'], float)


class TestPerformance:
    """Performance tests for features."""
    
    def test_feature_calculation_speed(
        self, features, sample_bars_1m, sample_bars_daily, sample_bars_1s
    ):
        """Test that features calculate quickly (<10ms each)."""
        import time
        
        overnight_bars = sample_bars_1m.head(30)
        
        start = time.time()
        all_features = features.calculate_all_features(
            sample_bars_1m,
            sample_bars_daily,
            sample_bars_1s,
            overnight_bars
        )
        end = time.time()
        
        elapsed_ms = (end - start) * 1000
        
        # Total should be <80ms (10ms per feature × 8)
        assert elapsed_ms < 100, f"Feature calculation took {elapsed_ms:.1f}ms (target: <100ms)"
        
        print(f"\nFeature calculation time: {elapsed_ms:.1f}ms")
        print(f"Average per feature: {elapsed_ms/8:.1f}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

