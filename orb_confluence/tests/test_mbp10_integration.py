"""
Unit Tests for MBP-10 Integration

Tests the MBP10Loader and OrderBookFeatures classes to ensure
they correctly load and process order book data.

Author: Nick Burner
Date: October 9, 2025
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orb_confluence.data.mbp10_loader import MBP10Loader
from orb_confluence.features.order_book_features import OrderBookFeatures


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_snapshot():
    """Create a mock order book snapshot for testing."""
    snapshot = {}
    
    # Best bid/ask
    snapshot['bid_px_00'] = 5650.00
    snapshot['ask_px_00'] = 5650.25
    snapshot['bid_sz_00'] = 100
    snapshot['ask_sz_00'] = 75
    snapshot['bid_ct_00'] = 5
    snapshot['ask_ct_00'] = 3
    
    # Deeper levels
    for level in range(1, 10):
        snapshot[f'bid_px_{level:02d}'] = 5650.00 - (level * 0.25)
        snapshot[f'ask_px_{level:02d}'] = 5650.25 + (level * 0.25)
        snapshot[f'bid_sz_{level:02d}'] = max(10, 100 - level * 10)
        snapshot[f'ask_sz_{level:02d}'] = max(10, 75 - level * 8)
        snapshot[f'bid_ct_{level:02d}'] = max(1, 5 - level)
        snapshot[f'ask_ct_{level:02d}'] = max(1, 3 - level)
    
    return snapshot


@pytest.fixture
def features_calc():
    """Create OrderBookFeatures calculator."""
    return OrderBookFeatures()


# ============================================================================
# TEST ORDER BOOK FEATURES
# ============================================================================

class TestOrderBookFeatures:
    """Test suite for OrderBookFeatures class."""
    
    def test_order_flow_imbalance(self, features_calc, mock_snapshot):
        """Test OFI calculation."""
        ofi = features_calc.order_flow_imbalance(mock_snapshot)
        
        # With bid=100, ask=75: OFI = (100-75)/(100+75) = 25/175 = 0.142857
        assert isinstance(ofi, float)
        assert -1.0 <= ofi <= 1.0
        assert abs(ofi - 0.142857) < 0.001
    
    def test_ofi_extremes(self, features_calc):
        """Test OFI at extreme values."""
        # All bids
        snapshot_all_bids = {'bid_sz_00': 100, 'ask_sz_00': 0}
        ofi_all_bids = features_calc.order_flow_imbalance(snapshot_all_bids)
        assert ofi_all_bids == 1.0
        
        # All asks
        snapshot_all_asks = {'bid_sz_00': 0, 'ask_sz_00': 100}
        ofi_all_asks = features_calc.order_flow_imbalance(snapshot_all_asks)
        assert ofi_all_asks == -1.0
        
        # Balanced
        snapshot_balanced = {'bid_sz_00': 100, 'ask_sz_00': 100}
        ofi_balanced = features_calc.order_flow_imbalance(snapshot_balanced)
        assert ofi_balanced == 0.0
    
    def test_depth_imbalance(self, features_calc, mock_snapshot):
        """Test depth imbalance calculation."""
        depth_imb = features_calc.depth_imbalance(mock_snapshot, levels=10)
        
        assert isinstance(depth_imb, float)
        assert -1.0 <= depth_imb <= 1.0
        # Should be positive since bids > asks in mock
        assert depth_imb > 0
    
    def test_microprice(self, features_calc, mock_snapshot):
        """Test microprice calculation."""
        microprice = features_calc.microprice(mock_snapshot)
        
        # Should be between bid and ask
        assert isinstance(microprice, float)
        assert mock_snapshot['bid_px_00'] <= microprice <= mock_snapshot['ask_px_00']
        
        # With bid_px=5650, ask_px=5650.25, bid_sz=100, ask_sz=75
        # Microprice = (5650*75 + 5650.25*100) / (100+75) = 991125.0 / 175 = 5663.57...
        # Wait, that's wrong. Let me recalculate:
        # Microprice = (5650*75 + 5650.25*100) / 175 = (423750 + 565025) / 175 = 5650.142857
        expected = (5650.00 * 75 + 5650.25 * 100) / 175
        assert abs(microprice - expected) < 0.01
    
    def test_volume_at_best(self, features_calc, mock_snapshot):
        """Test VAB calculation."""
        vab = features_calc.volume_at_best(mock_snapshot)
        
        assert isinstance(vab, int)
        assert vab == 175  # 100 + 75
    
    def test_liquidity_ratio(self, features_calc, mock_snapshot):
        """Test liquidity concentration."""
        ratio = features_calc.liquidity_ratio(mock_snapshot, levels=10)
        
        assert isinstance(ratio, float)
        assert 0.0 <= ratio <= 1.0
        # Should be less than 1 since liquidity is spread
        assert ratio < 1.0
    
    def test_spread(self, features_calc, mock_snapshot):
        """Test spread calculation."""
        spread = features_calc.spread(mock_snapshot)
        
        assert isinstance(spread, float)
        assert spread == 0.25  # 5650.25 - 5650.00
    
    def test_detect_large_orders(self, features_calc, mock_snapshot):
        """Test large order detection."""
        large_orders = features_calc.detect_large_orders(mock_snapshot, threshold=50, levels=10)
        
        assert 'bids' in large_orders
        assert 'asks' in large_orders
        assert isinstance(large_orders['bids'], list)
        assert isinstance(large_orders['asks'], list)
        
        # At least best bid (100) should be detected
        assert len(large_orders['bids']) >= 1
        # At least best ask (75) should be detected
        assert len(large_orders['asks']) >= 1
    
    def test_find_support_resistance(self, features_calc, mock_snapshot):
        """Test support/resistance finder."""
        # Find support (LONG)
        support_price, support_size = features_calc.find_support_resistance(mock_snapshot, 'LONG')
        assert support_price is not None
        assert support_size > 0
        assert support_size == 100  # Best bid is largest
        
        # Find resistance (SHORT)
        resistance_price, resistance_size = features_calc.find_support_resistance(mock_snapshot, 'SHORT')
        assert resistance_price is not None
        assert resistance_size > 0
        assert resistance_size == 75  # Best ask is largest
    
    def test_calculate_all_features(self, features_calc, mock_snapshot):
        """Test batch feature calculation."""
        features = features_calc.calculate_all_features(mock_snapshot)
        
        # Check all expected keys
        expected_keys = [
            'ofi', 'depth_imbalance', 'microprice', 
            'volume_at_best', 'liquidity_ratio', 'spread',
            'large_bid_count', 'large_ask_count'
        ]
        
        for key in expected_keys:
            assert key in features
        
        # Validate types and ranges
        assert -1.0 <= features['ofi'] <= 1.0
        assert -1.0 <= features['depth_imbalance'] <= 1.0
        assert features['microprice'] > 0
        assert features['volume_at_best'] > 0
        assert 0.0 <= features['liquidity_ratio'] <= 1.0
        assert features['spread'] >= 0


# ============================================================================
# TEST MBP10 LOADER (INTEGRATION TESTS - require data)
# ============================================================================

class TestMBP10Loader:
    """Test suite for MBP10Loader class."""
    
    @pytest.fixture
    def data_dir(self):
        """Get data directory path."""
        return "data_cache/GLBX-20251008-HHT7VXJSSJ"
    
    @pytest.fixture
    def loader(self, data_dir):
        """Create MBP10Loader instance."""
        data_path = Path(data_dir)
        if not data_path.exists():
            pytest.skip(f"Data directory not found: {data_dir}")
        return MBP10Loader(data_directory=data_dir)
    
    def test_loader_init(self, loader):
        """Test loader initialization."""
        assert loader is not None
        assert loader.data_dir.exists()
    
    def test_get_snapshot_at(self, loader):
        """Test getting snapshot at specific time."""
        # Try to get snapshot from Sept 15
        snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
        
        if snapshot is None:
            pytest.skip("No data found for 2025-09-15 09:30:00")
        
        # Validate snapshot structure
        assert 'bid_px_00' in snapshot
        assert 'ask_px_00' in snapshot
        assert 'bid_sz_00' in snapshot
        assert 'ask_sz_00' in snapshot
        
        # Validate values
        assert snapshot['bid_px_00'] > 0
        assert snapshot['ask_px_00'] > 0
        assert snapshot['ask_px_00'] > snapshot['bid_px_00']  # Ask > Bid
    
    def test_get_ofi_series(self, loader):
        """Test OFI time series extraction."""
        ofi_series = loader.get_ofi_series(
            start="2025-09-15 09:30:00",
            end="2025-09-15 10:00:00"
        )
        
        if len(ofi_series) == 0:
            pytest.skip("No data found for time range")
        
        # Validate series
        assert len(ofi_series) > 0
        assert all(-1.0 <= v <= 1.0 for v in ofi_series if not pd.isna(v))
    
    def test_get_depth_imbalance_series(self, loader):
        """Test depth imbalance time series."""
        depth_series = loader.get_depth_imbalance_series(
            start="2025-09-15 09:30:00",
            end="2025-09-15 10:00:00",
            levels=10
        )
        
        if len(depth_series) == 0:
            pytest.skip("No data found for time range")
        
        # Validate series
        assert len(depth_series) > 0
        assert all(-1.0 <= v <= 1.0 for v in depth_series if not pd.isna(v))
    
    def test_cache_functionality(self, loader):
        """Test data caching."""
        # First load
        snapshot1 = loader.get_snapshot_at("2025-09-15", "09:30:00")
        cache_size_1 = len(loader._cache)
        
        # Second load (should use cache)
        snapshot2 = loader.get_snapshot_at("2025-09-15", "09:30:01")
        cache_size_2 = len(loader._cache)
        
        # Cache size should be same (same date)
        assert cache_size_1 == cache_size_2
        
        # Clear cache
        loader.clear_cache()
        assert len(loader._cache) == 0


# ============================================================================
# INTEGRATION TESTS (FEATURES + LOADER)
# ============================================================================

class TestIntegration:
    """Integration tests combining loader and features."""
    
    @pytest.fixture
    def setup(self):
        """Set up loader and features calculator."""
        data_dir = "data_cache/GLBX-20251008-HHT7VXJSSJ"
        if not Path(data_dir).exists():
            pytest.skip(f"Data directory not found: {data_dir}")
        
        loader = MBP10Loader(data_directory=data_dir)
        features_calc = OrderBookFeatures()
        
        return loader, features_calc
    
    def test_full_pipeline(self, setup):
        """Test complete pipeline: load data -> calculate features."""
        loader, features_calc = setup
        
        # Get snapshot
        snapshot = loader.get_snapshot_at("2025-09-15", "09:30:00")
        
        if snapshot is None:
            pytest.skip("No data available")
        
        # Calculate features
        features = features_calc.calculate_all_features(snapshot)
        
        # Validate
        assert 'ofi' in features
        assert 'depth_imbalance' in features
        assert 'microprice' in features
        
        print("\n=== Integration Test Results ===")
        print(f"OFI: {features['ofi']:.4f}")
        print(f"Depth Imbalance: {features['depth_imbalance']:.4f}")
        print(f"Microprice: ${features['microprice']:.2f}")
        print(f"Volume at Best: {features['volume_at_best']}")
    
    def test_exhaustion_detection(self, setup):
        """Test exhaustion detection with real data."""
        loader, features_calc = setup
        
        # Get time series
        df = loader.get_range(
            start="2025-09-15 09:30:00",
            end="2025-09-15 09:35:00"
        )
        
        if len(df) < 10:
            pytest.skip("Insufficient data")
        
        # Test exhaustion for SHORT position
        is_exhausted, reason = features_calc.detect_exhaustion(
            df_recent=df.tail(20),
            direction='SHORT',
            window=10
        )
        
        assert isinstance(is_exhausted, bool)
        assert isinstance(reason, str)
        
        print(f"\n=== Exhaustion Test ===")
        print(f"Exhausted: {is_exhausted}")
        print(f"Reason: {reason}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])

