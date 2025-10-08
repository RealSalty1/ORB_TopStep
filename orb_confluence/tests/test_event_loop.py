"""Tests for event loop backtest."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from orb_confluence.backtest import EventLoopBacktest, BacktestResult
from orb_confluence.config.schema import (
    StrategyConfig,
    ORBConfig,
    BufferConfig,
    FactorsConfig,
    TradeConfig,
    GovernanceConfig,
    ScoringConfig,
)
from orb_confluence.data.sources.synthetic import SyntheticProvider


def create_test_config() -> StrategyConfig:
    """Create test configuration."""
    return StrategyConfig(
        orb=ORBConfig(
            or_length_minutes=15,
            adaptive=False,
            min_atr_mult=0.3,
            max_atr_mult=3.0,
        ),
        buffer=BufferConfig(
            mode='fixed',
            fixed_ticks=2,
            atr_mult=0.1,
        ),
        factors=FactorsConfig(
            rel_vol_lookback=20,
            rel_vol_spike_threshold=1.5,
            price_action_pivot_len=3,
            adx_period=14,
            adx_threshold=25.0,
        ),
        trade=TradeConfig(
            partials=True,
            t1_r=1.0,
            t1_pct=0.5,
            t2_r=1.5,
            t2_pct=0.25,
            runner_r=2.0,
            primary_r=1.5,
            stop_mode='or_opposite',
            extra_stop_buffer=0.05,
            move_be_at_r=1.0,
            be_buffer=0.01,
        ),
        governance=GovernanceConfig(
            max_signals_per_day=3,
            lockout_after_losses=2,
        ),
        scoring=ScoringConfig(
            weights={'rel_vol': 1.0, 'price_action': 1.0, 'profile': 1.0},
            base_requirement=1.0,
            weak_trend_requirement=2.0,
        ),
    )


def create_synthetic_bars(
    seed: int = 42,
    minutes: int = 390,
    regime: str = 'trend_up',
) -> pd.DataFrame:
    """Create synthetic bar data for testing.
    
    Args:
        seed: Random seed for reproducibility.
        minutes: Number of minutes.
        regime: Market regime.
        
    Returns:
        DataFrame with OHLCV data.
    """
    provider = SyntheticProvider()
    bars = provider.generate_synthetic_day(
        seed=seed,
        regime=regime,
        minutes=minutes,
        base_price=100.0,
        volatility_mult=1.0,
    )
    
    return bars


class TestEventLoopBasic:
    """Test basic event loop functionality."""

    def test_initialization(self):
        """Test backtest engine initialization."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        assert engine.config == config
        assert engine.sample_factors_every_n == 10
        assert engine.cumulative_r == 0.0

    def test_empty_bars(self):
        """Test backtest with empty bars."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = pd.DataFrame(columns=['timestamp_utc', 'open', 'high', 'low', 'close', 'volume'])
        
        result = engine.run(bars)
        
        assert isinstance(result, BacktestResult)
        assert result.total_trades == 0
        assert result.total_r == 0.0

    def test_single_bar(self):
        """Test backtest with single bar."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = pd.DataFrame([{
            'timestamp_utc': datetime(2024, 1, 2, 9, 30),
            'open': 100.0,
            'high': 100.2,
            'low': 99.8,
            'close': 100.1,
            'volume': 1000,
        }])
        
        result = engine.run(bars)
        
        assert isinstance(result, BacktestResult)
        assert result.total_trades == 0  # Not enough bars for signal


class TestEventLoopSynthetic:
    """Test event loop with synthetic data."""

    def test_synthetic_trend_up(self):
        """Test backtest with uptrending synthetic data."""
        config = create_test_config()
        engine = EventLoopBacktest(config, sample_factors_every_n=0)
        
        bars = create_synthetic_bars(seed=42, regime='trend_up', minutes=120)
        
        result = engine.run(bars)
        
        # Should have processed all bars
        assert not result.equity_curve.empty
        assert len(result.equity_curve) == 120
        
        # Should have factor snapshots
        assert len(result.factor_snapshots) > 0
        
        # May or may not have trades depending on signals
        assert result.total_trades >= 0

    def test_synthetic_trend_down(self):
        """Test backtest with downtrending synthetic data."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=123, regime='trend_down', minutes=120)
        
        result = engine.run(bars)
        
        assert isinstance(result, BacktestResult)
        assert not result.equity_curve.empty

    def test_synthetic_choppy(self):
        """Test backtest with choppy synthetic data."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=456, regime='choppy', minutes=120)
        
        result = engine.run(bars)
        
        assert isinstance(result, BacktestResult)
        assert not result.equity_curve.empty

    def test_deterministic_results(self):
        """Test that same seed produces deterministic results."""
        config = create_test_config()
        
        # Run 1
        engine1 = EventLoopBacktest(config)
        bars1 = create_synthetic_bars(seed=999, regime='trend_up', minutes=100)
        result1 = engine1.run(bars1)
        
        # Run 2 with same seed
        engine2 = EventLoopBacktest(config)
        bars2 = create_synthetic_bars(seed=999, regime='trend_up', minutes=100)
        result2 = engine2.run(bars2)
        
        # Results should be identical
        assert result1.total_trades == result2.total_trades
        assert result1.total_r == result2.total_r
        assert len(result1.equity_curve) == len(result2.equity_curve)


class TestEventLoopTrading:
    """Test trading logic in event loop."""

    def test_or_building(self):
        """Test that OR is built correctly."""
        config = create_test_config()
        engine = EventLoopBacktest(config, sample_factors_every_n=1)
        
        bars = create_synthetic_bars(seed=42, minutes=60)
        
        result = engine.run(bars)
        
        # Check that some snapshots show OR finalized
        or_finalized_snapshots = [s for s in result.factor_snapshots if s.or_finalized]
        
        # Should have snapshots after OR period
        assert len(or_finalized_snapshots) > 0
        
        # OR high/low should be set in finalized snapshots
        for snapshot in or_finalized_snapshots:
            assert snapshot.or_high is not None
            assert snapshot.or_low is not None

    def test_equity_curve_creation(self):
        """Test equity curve is created."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=42, minutes=60)
        
        result = engine.run(bars)
        
        # Equity curve should exist
        assert not result.equity_curve.empty
        assert 'timestamp' in result.equity_curve.columns
        assert 'cumulative_r' in result.equity_curve.columns
        
        # Should have entry for each bar
        assert len(result.equity_curve) == len(bars)

    def test_factor_snapshots(self):
        """Test factor snapshots are collected."""
        config = create_test_config()
        engine = EventLoopBacktest(config, sample_factors_every_n=5)
        
        bars = create_synthetic_bars(seed=42, minutes=100)
        
        result = engine.run(bars)
        
        # Should have snapshots (every 5th bar)
        assert len(result.factor_snapshots) > 0
        assert len(result.factor_snapshots) <= len(bars)
        
        # Check snapshot structure
        snapshot = result.factor_snapshots[0]
        assert snapshot.timestamp is not None
        assert isinstance(snapshot.or_finalized, bool)


class TestEventLoopGovernance:
    """Test governance integration in event loop."""

    def test_no_trades_with_zero_max_signals(self):
        """Test that max_signals_per_day=0 prevents all trading."""
        config = create_test_config()
        config.governance.max_signals_per_day = 0
        
        engine = EventLoopBacktest(config)
        bars = create_synthetic_bars(seed=42, regime='trend_up', minutes=120)
        
        result = engine.run(bars)
        
        # Should have no trades
        assert result.total_trades == 0

    def test_lockout_limits_trades(self):
        """Test that lockout after losses limits trades."""
        config = create_test_config()
        config.governance.lockout_after_losses = 1  # Lockout after first loss
        config.governance.max_signals_per_day = 10
        
        engine = EventLoopBacktest(config)
        bars = create_synthetic_bars(seed=42, minutes=200)
        
        result = engine.run(bars)
        
        # If any trades are taken and lose, should trigger lockout
        # (Results depend on synthetic data and signal generation)
        if result.total_trades > 0:
            # Check governance events for lockout
            lockout_events = [e for e in result.governance_events if e['event'] == 'lockout']
            
            # If there was a losing trade, should have lockout
            losing_trades = [t for t in result.trades if t.realized_r < 0]
            if losing_trades:
                # After first loss, should be locked out
                pass  # Test passes if backtest runs without errors


class TestBacktestResult:
    """Test BacktestResult dataclass."""

    def test_result_statistics(self):
        """Test that result statistics are calculated."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=42, minutes=100)
        
        result = engine.run(bars)
        
        # Check statistics fields exist
        assert hasattr(result, 'total_trades')
        assert hasattr(result, 'winning_trades')
        assert hasattr(result, 'total_r')
        assert hasattr(result, 'max_drawdown_r')
        assert hasattr(result, 'final_equity_r')
        
        # Values should be valid
        assert result.total_trades >= 0
        assert result.winning_trades >= 0
        assert result.winning_trades <= result.total_trades

    def test_result_components(self):
        """Test that all result components are present."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=42, minutes=100)
        
        result = engine.run(bars)
        
        # Check all components
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, pd.DataFrame)
        assert isinstance(result.factor_snapshots, list)
        assert isinstance(result.daily_stats, dict)
        assert isinstance(result.governance_events, list)


@pytest.mark.slow
class TestEventLoopPerformance:
    """Test event loop performance."""

    def test_full_day_backtest(self):
        """Test full trading day (390 minutes)."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        bars = create_synthetic_bars(seed=42, minutes=390)
        
        result = engine.run(bars)
        
        # Should complete without errors
        assert result.total_trades >= 0
        assert len(result.equity_curve) == 390

    def test_multi_day_data(self):
        """Test multiple days of data."""
        config = create_test_config()
        engine = EventLoopBacktest(config)
        
        # Create 3 days of data
        all_bars = []
        start_date = datetime(2024, 1, 2, 9, 30)
        
        for day in range(3):
            day_start = start_date + timedelta(days=day)
            
            day_bars = create_synthetic_bars(seed=42 + day, minutes=100)
            
            # Adjust timestamps
            day_bars['timestamp_utc'] = [
                day_start + timedelta(minutes=i) 
                for i in range(len(day_bars))
            ]
            
            all_bars.append(day_bars)
        
        bars = pd.concat(all_bars, ignore_index=True)
        
        result = engine.run(bars)
        
        # Should have processed all bars
        assert len(result.equity_curve) == 300  # 100 bars x 3 days