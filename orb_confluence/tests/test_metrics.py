"""Tests for performance metrics."""

from datetime import datetime, timedelta

import pytest

from orb_confluence.analytics.metrics import (
    compute_equity_curve,
    compute_drawdowns,
    compute_metrics,
    PerformanceMetrics,
)
from orb_confluence.strategy.trade_state import ActiveTrade


def create_dummy_trade(
    trade_id: str,
    realized_r: float,
    entry_time: datetime,
    duration_minutes: int = 60,
) -> ActiveTrade:
    """Create dummy trade for testing."""
    return ActiveTrade(
        trade_id=trade_id,
        direction='long',
        entry_timestamp=entry_time,
        entry_price=100.0,
        stop_price_initial=99.0,
        stop_price_current=99.0,
        targets=[(101.0, 1.0)],
        exit_timestamp=entry_time + timedelta(minutes=duration_minutes),
        exit_price=101.0 if realized_r > 0 else 99.0,
        realized_r=realized_r,
    )


class TestComputeEquityCurve:
    """Test compute_equity_curve function."""

    def test_empty_trades(self):
        """Test with empty trade list."""
        equity = compute_equity_curve([])
        
        assert equity.empty
        assert list(equity.columns) == ['trade_number', 'cumulative_r', 'drawdown_r', 'drawdown_pct']

    def test_single_trade(self):
        """Test with single trade."""
        trades = [create_dummy_trade('T1', 1.0, datetime(2024, 1, 2, 10, 0))]
        
        equity = compute_equity_curve(trades)
        
        assert len(equity) == 1
        assert equity['cumulative_r'].iloc[0] == pytest.approx(1.0)
        assert equity['drawdown_r'].iloc[0] == pytest.approx(0.0)  # At peak

    def test_winning_streak(self):
        """Test with winning streak."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 1.0, base_time),
            create_dummy_trade('T2', 0.5, base_time + timedelta(hours=1)),
            create_dummy_trade('T3', 1.5, base_time + timedelta(hours=2)),
        ]
        
        equity = compute_equity_curve(trades)
        
        assert len(equity) == 3
        assert equity['cumulative_r'].iloc[0] == pytest.approx(1.0)
        assert equity['cumulative_r'].iloc[1] == pytest.approx(1.5)
        assert equity['cumulative_r'].iloc[2] == pytest.approx(3.0)
        
        # No drawdown during winning streak
        assert (equity['drawdown_r'] == 0.0).all()

    def test_drawdown_calculation(self):
        """Test drawdown calculation."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 2.0, base_time),  # Up to 2R
            create_dummy_trade('T2', -1.0, base_time + timedelta(hours=1)),  # Down to 1R
            create_dummy_trade('T3', 1.0, base_time + timedelta(hours=2)),  # Back to 2R
        ]
        
        equity = compute_equity_curve(trades)
        
        # Trade 1: 2R, no DD
        assert equity['drawdown_r'].iloc[0] == pytest.approx(0.0)
        
        # Trade 2: 1R, DD of -1R
        assert equity['drawdown_r'].iloc[1] == pytest.approx(-1.0)
        
        # Trade 3: 2R, back to peak, no DD
        assert equity['drawdown_r'].iloc[2] == pytest.approx(0.0)


class TestComputeDrawdowns:
    """Test compute_drawdowns function."""

    def test_no_drawdowns(self):
        """Test with no drawdowns (all wins)."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 1.0, base_time),
            create_dummy_trade('T2', 1.0, base_time + timedelta(hours=1)),
        ]
        
        equity = compute_equity_curve(trades)
        drawdowns = compute_drawdowns(equity)
        
        assert drawdowns.empty

    def test_single_drawdown(self):
        """Test with single drawdown period."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 2.0, base_time),  # Peak at 2R
            create_dummy_trade('T2', -1.0, base_time + timedelta(hours=1)),  # 1R
            create_dummy_trade('T3', -0.5, base_time + timedelta(hours=2)),  # 0.5R (lowest)
            create_dummy_trade('T4', 1.5, base_time + timedelta(hours=3)),  # Back to 2R
        ]
        
        equity = compute_equity_curve(trades)
        drawdowns = compute_drawdowns(equity)
        
        assert len(drawdowns) == 1
        assert drawdowns['depth_r'].iloc[0] == pytest.approx(-1.5)  # 2R - 0.5R
        assert drawdowns['duration_trades'].iloc[0] == 3  # Trades 2, 3, 4


class TestComputeMetrics:
    """Test compute_metrics function."""

    def test_empty_trades(self):
        """Test with empty trade list."""
        metrics = compute_metrics([])
        
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.total_r == 0.0

    def test_all_winners(self):
        """Test with all winning trades."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 1.0, base_time),
            create_dummy_trade('T2', 1.5, base_time + timedelta(hours=1)),
            create_dummy_trade('T3', 0.5, base_time + timedelta(hours=2)),
        ]
        
        metrics = compute_metrics(trades)
        
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 0
        assert metrics.win_rate == 1.0
        assert metrics.total_r == pytest.approx(3.0)
        assert metrics.average_r == pytest.approx(1.0)
        assert metrics.profit_factor == float('inf')  # No losses

    def test_mixed_trades(self):
        """Test with mixed wins and losses."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 2.0, base_time),  # Win
            create_dummy_trade('T2', -1.0, base_time + timedelta(hours=1)),  # Loss
            create_dummy_trade('T3', 1.5, base_time + timedelta(hours=2)),  # Win
            create_dummy_trade('T4', -0.5, base_time + timedelta(hours=3)),  # Loss
        ]
        
        metrics = compute_metrics(trades)
        
        assert metrics.total_trades == 4
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 2
        assert metrics.win_rate == 0.5
        assert metrics.total_r == pytest.approx(2.0)  # 2 + 1.5 - 1 - 0.5
        assert metrics.average_r == pytest.approx(0.5)
        
        # Profit factor = gross profit / gross loss = 3.5 / 1.5 = 2.33
        assert metrics.profit_factor == pytest.approx(3.5 / 1.5, rel=0.01)
        
        # Winners/losers
        assert metrics.avg_winner_r == pytest.approx(1.75)  # (2.0 + 1.5) / 2
        assert metrics.avg_loser_r == pytest.approx(-0.75)  # (-1.0 + -0.5) / 2
        assert metrics.largest_winner_r == pytest.approx(2.0)
        assert metrics.largest_loser_r == pytest.approx(-1.0)

    def test_consecutive_wins_losses(self):
        """Test consecutive wins and losses counting."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 1.0, base_time),  # Win
            create_dummy_trade('T2', 1.0, base_time + timedelta(hours=1)),  # Win
            create_dummy_trade('T3', 1.0, base_time + timedelta(hours=2)),  # Win (3 consecutive)
            create_dummy_trade('T4', -1.0, base_time + timedelta(hours=3)),  # Loss
            create_dummy_trade('T5', -1.0, base_time + timedelta(hours=4)),  # Loss (2 consecutive)
            create_dummy_trade('T6', 1.0, base_time + timedelta(hours=5)),  # Win
        ]
        
        metrics = compute_metrics(trades)
        
        assert metrics.consecutive_wins == 3
        assert metrics.consecutive_losses == 2

    def test_trade_duration(self):
        """Test average trade duration calculation."""
        base_time = datetime(2024, 1, 2, 10, 0)
        trades = [
            create_dummy_trade('T1', 1.0, base_time, duration_minutes=30),
            create_dummy_trade('T2', 1.0, base_time + timedelta(hours=1), duration_minutes=60),
            create_dummy_trade('T3', 1.0, base_time + timedelta(hours=2), duration_minutes=90),
        ]
        
        metrics = compute_metrics(trades)
        
        assert metrics.avg_trade_duration_minutes == pytest.approx(60.0)  # (30 + 60 + 90) / 3


class TestPerformanceMetrics:
    """Test PerformanceMetrics dataclass."""

    def test_metrics_structure(self):
        """Test metrics dataclass structure."""
        metrics = PerformanceMetrics(
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            total_r=5.0,
            average_r=0.5,
            median_r=0.4,
            expectancy=0.5,
            profit_factor=2.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown_r=-2.0,
            max_drawdown_pct=-15.0,
            avg_winner_r=1.5,
            avg_loser_r=-1.0,
            largest_winner_r=3.0,
            largest_loser_r=-2.0,
            consecutive_wins=3,
            consecutive_losses=2,
            avg_trade_duration_minutes=45.0,
        )
        
        assert metrics.total_trades == 10
        assert metrics.win_rate == 0.6
        assert metrics.sharpe_ratio == 1.5
