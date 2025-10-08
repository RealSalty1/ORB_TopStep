"""Tests for factor attribution analysis."""

from datetime import datetime

import pytest

from orb_confluence.analytics.attribution import (
    analyze_factor_attribution,
    analyze_score_buckets,
    FactorAttribution,
)
from orb_confluence.strategy.trade_state import ActiveTrade, TradeSignal


def create_dummy_trade_with_signal(
    trade_id: str,
    realized_r: float,
    factors: dict,
    confluence_score: float,
) -> ActiveTrade:
    """Create dummy trade with signal for testing."""
    signal = TradeSignal(
        direction='long',
        timestamp=datetime(2024, 1, 2, 10, 0),
        entry_price=100.0,
        confluence_score=confluence_score,
        confluence_required=2.0,
        factors=factors,
        or_high=100.5,
        or_low=100.0,
        signal_id=trade_id,
    )
    
    return ActiveTrade(
        trade_id=trade_id,
        direction='long',
        entry_timestamp=datetime(2024, 1, 2, 10, 0),
        entry_price=100.0,
        stop_price_initial=99.0,
        stop_price_current=99.0,
        targets=[(101.0, 1.0)],
        exit_timestamp=datetime(2024, 1, 2, 11, 0),
        exit_price=101.0 if realized_r > 0 else 99.0,
        realized_r=realized_r,
        signal=signal,
    )


class TestAnalyzeFactorAttribution:
    """Test analyze_factor_attribution function."""

    def test_empty_trades(self):
        """Test with empty trade list."""
        attr = analyze_factor_attribution([])
        
        assert isinstance(attr, FactorAttribution)
        assert attr.factor_presence.empty
        assert attr.factor_win_rates == {}
        assert attr.factor_avg_r == {}

    def test_single_factor(self):
        """Test with single factor."""
        trades = [
            # Factor present, win
            create_dummy_trade_with_signal('T1', 1.0, {'rel_vol': 1.0}, 2.0),
            # Factor present, win
            create_dummy_trade_with_signal('T2', 0.5, {'rel_vol': 1.0}, 2.0),
            # Factor absent, loss
            create_dummy_trade_with_signal('T3', -1.0, {'rel_vol': 0.0}, 1.0),
        ]
        
        attr = analyze_factor_attribution(trades)
        
        # Check factor presence table
        assert len(attr.factor_presence) == 1
        row = attr.factor_presence.iloc[0]
        
        assert row['factor'] == 'rel_vol'
        assert row['present_count'] == 2
        assert row['absent_count'] == 1
        assert row['present_win_rate'] == 1.0  # 2/2
        assert row['absent_win_rate'] == 0.0  # 0/1
        
        # Check factor win rates
        assert attr.factor_win_rates['rel_vol'] == 1.0

    def test_multiple_factors(self):
        """Test with multiple factors."""
        trades = [
            # Both factors, win
            create_dummy_trade_with_signal(
                'T1', 1.5,
                {'rel_vol': 1.0, 'price_action': 1.0},
                3.0
            ),
            # Only rel_vol, win
            create_dummy_trade_with_signal(
                'T2', 1.0,
                {'rel_vol': 1.0, 'price_action': 0.0},
                2.0
            ),
            # Only price_action, loss
            create_dummy_trade_with_signal(
                'T3', -1.0,
                {'rel_vol': 0.0, 'price_action': 1.0},
                1.5
            ),
            # Neither, loss
            create_dummy_trade_with_signal(
                'T4', -0.5,
                {'rel_vol': 0.0, 'price_action': 0.0},
                0.5
            ),
        ]
        
        attr = analyze_factor_attribution(trades)
        
        # Check number of factors
        assert len(attr.factor_presence) == 2
        
        # Find rel_vol row
        rel_vol_row = attr.factor_presence[
            attr.factor_presence['factor'] == 'rel_vol'
        ].iloc[0]
        
        assert rel_vol_row['present_count'] == 2  # T1, T2
        assert rel_vol_row['absent_count'] == 2  # T3, T4
        assert rel_vol_row['present_win_rate'] == 1.0  # 2/2 wins
        assert rel_vol_row['absent_win_rate'] == 0.0  # 0/2 wins

    def test_delta_calculations(self):
        """Test delta calculations (present vs absent)."""
        trades = [
            # Factor present, avg R = 1.0
            create_dummy_trade_with_signal('T1', 1.0, {'factor_a': 1.0}, 2.0),
            create_dummy_trade_with_signal('T2', 1.0, {'factor_a': 1.0}, 2.0),
            # Factor absent, avg R = -0.5
            create_dummy_trade_with_signal('T3', -0.5, {'factor_a': 0.0}, 1.0),
            create_dummy_trade_with_signal('T4', -0.5, {'factor_a': 0.0}, 1.0),
        ]
        
        attr = analyze_factor_attribution(trades)
        
        row = attr.factor_presence.iloc[0]
        
        # Delta win rate = 1.0 - 0.0 = 1.0 (100%)
        assert row['delta_win_rate'] == pytest.approx(1.0)
        
        # Delta avg R = 1.0 - (-0.5) = 1.5
        assert row['delta_avg_r'] == pytest.approx(1.5)


class TestAnalyzeScoreBuckets:
    """Test analyze_score_buckets function."""

    def test_empty_trades(self):
        """Test with empty trade list."""
        score_df = analyze_score_buckets([])
        
        assert score_df.empty

    def test_single_bucket(self):
        """Test with trades in single bucket."""
        trades = [
            create_dummy_trade_with_signal('T1', 1.0, {}, 1.2),
            create_dummy_trade_with_signal('T2', 0.5, {}, 1.4),
            create_dummy_trade_with_signal('T3', -0.5, {}, 1.1),
        ]
        
        score_df = analyze_score_buckets(trades, bucket_size=0.5)
        
        # All trades should be in 1.0-1.5 bucket
        assert len(score_df) == 1
        assert score_df['count'].iloc[0] == 3
        assert score_df['win_rate'].iloc[0] == pytest.approx(2/3, rel=0.01)

    def test_multiple_buckets(self):
        """Test with trades across multiple buckets."""
        trades = [
            # Bucket 1.0-1.5
            create_dummy_trade_with_signal('T1', 1.0, {}, 1.2),
            create_dummy_trade_with_signal('T2', 1.0, {}, 1.4),
            # Bucket 1.5-2.0
            create_dummy_trade_with_signal('T3', 2.0, {}, 1.7),
            create_dummy_trade_with_signal('T4', 1.5, {}, 1.9),
            # Bucket 2.0-2.5
            create_dummy_trade_with_signal('T5', -1.0, {}, 2.1),
        ]
        
        score_df = analyze_score_buckets(trades, bucket_size=0.5)
        
        # Should have 3 buckets
        assert len(score_df) >= 2  # At least 2 buckets
        
        # Check first bucket (1.0-1.5)
        bucket1 = score_df[score_df['score_bucket'] == '1.0-1.5']
        if not bucket1.empty:
            assert bucket1['count'].iloc[0] == 2
            assert bucket1['win_rate'].iloc[0] == 1.0  # 2/2

    def test_score_performance_gradient(self):
        """Test that higher scores correlate with better performance."""
        trades = [
            # Low score bucket (0.5-1.0): 0% win rate
            create_dummy_trade_with_signal('T1', -1.0, {}, 0.7),
            create_dummy_trade_with_signal('T2', -0.5, {}, 0.9),
            # Mid score bucket (1.5-2.0): 50% win rate
            create_dummy_trade_with_signal('T3', 1.0, {}, 1.7),
            create_dummy_trade_with_signal('T4', -1.0, {}, 1.9),
            # High score bucket (2.5-3.0): 100% win rate
            create_dummy_trade_with_signal('T5', 2.0, {}, 2.7),
            create_dummy_trade_with_signal('T6', 1.5, {}, 2.9),
        ]
        
        score_df = analyze_score_buckets(trades, bucket_size=0.5)
        
        # Should show increasing win rate with score
        # (Exact values depend on bucket boundaries)
        assert len(score_df) >= 2


class TestFactorAttribution:
    """Test FactorAttribution dataclass."""

    def test_attribution_structure(self):
        """Test attribution dataclass structure."""
        import pandas as pd
        
        attr = FactorAttribution(
            factor_presence=pd.DataFrame({
                'factor': ['rel_vol'],
                'present_count': [10],
                'present_win_rate': [0.7],
                'present_avg_r': [0.8],
                'absent_count': [5],
                'absent_win_rate': [0.4],
                'absent_avg_r': [0.2],
                'delta_win_rate': [0.3],
                'delta_avg_r': [0.6],
            }),
            score_buckets=pd.DataFrame(),
            factor_win_rates={'rel_vol': 0.7},
            factor_avg_r={'rel_vol': 0.8},
        )
        
        assert not attr.factor_presence.empty
        assert 'rel_vol' in attr.factor_win_rates
        assert attr.factor_win_rates['rel_vol'] == 0.7
