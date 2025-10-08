"""Tests for HTML report generation."""

from datetime import datetime
from pathlib import Path

import pytest

from orb_confluence.reporting import generate_report
from orb_confluence.backtest.event_loop import BacktestResult
from orb_confluence.config.schema import (
    StrategyConfig,
    ORBConfig,
    BufferConfig,
    FactorsConfig,
    TradeConfig,
    GovernanceConfig,
    ScoringConfig,
)
from orb_confluence.strategy.trade_state import ActiveTrade, TradeSignal
import pandas as pd


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


def create_dummy_trade(
    trade_id: str,
    realized_r: float,
    factors: dict,
    score: float,
) -> ActiveTrade:
    """Create dummy trade with signal."""
    signal = TradeSignal(
        direction='long',
        timestamp=datetime(2024, 1, 2, 10, 0),
        entry_price=100.0,
        confluence_score=score,
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


class TestGenerateReport:
    """Test generate_report function."""

    def test_minimal_report_no_trades(self):
        """Test report generation with no trades."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check HTML structure
        assert '<!DOCTYPE html>' in html
        assert '<title>' in html
        assert 'ORB Confluence Strategy' in html
        assert 'Performance Summary' in html
        
        # Check metrics show zero
        assert 'Total R' in html
        assert '0.00R' in html

    def test_report_with_trades(self):
        """Test report generation with trades."""
        config = create_test_config()
        
        trades = [
            create_dummy_trade('T1', 1.5, {'rel_vol': 1.0, 'price_action': 1.0}, 2.5),
            create_dummy_trade('T2', -1.0, {'rel_vol': 0.0, 'price_action': 1.0}, 1.5),
            create_dummy_trade('T3', 2.0, {'rel_vol': 1.0, 'price_action': 1.0}, 3.0),
        ]
        
        equity_df = pd.DataFrame([
            {'timestamp': datetime(2024, 1, 2, 10, 0), 'cumulative_r': 1.5},
            {'timestamp': datetime(2024, 1, 2, 11, 0), 'cumulative_r': 0.5},
            {'timestamp': datetime(2024, 1, 2, 12, 0), 'cumulative_r': 2.5},
        ])
        
        result = BacktestResult(
            trades=trades,
            equity_curve=equity_df,
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check metrics
        assert 'Total R' in html
        assert '2.50R' in html or '2.5R' in html  # Total: 1.5 - 1.0 + 2.0 = 2.5
        
        # Check win rate
        assert 'Win Rate' in html
        assert '66.7%' in html or '67%' in html  # 2/3
        
        # Check trade count
        assert '3' in html  # Total trades

    def test_report_config_section(self):
        """Test that config section is included."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check config values
        assert '15 minutes' in html  # OR length
        assert 'or_opposite' in html  # Stop mode
        assert 'Enabled' in html  # Partials
        assert '1.0R' in html  # T1 target

    def test_report_factor_attribution(self):
        """Test factor attribution section."""
        config = create_test_config()
        
        trades = [
            create_dummy_trade('T1', 1.0, {'rel_vol': 1.0, 'price_action': 1.0}, 2.5),
            create_dummy_trade('T2', 1.0, {'rel_vol': 1.0, 'price_action': 0.0}, 2.0),
            create_dummy_trade('T3', -1.0, {'rel_vol': 0.0, 'price_action': 1.0}, 1.5),
        ]
        
        result = BacktestResult(
            trades=trades,
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check attribution section
        assert 'Factor Attribution' in html
        assert 'rel_vol' in html
        assert 'price_action' in html

    def test_report_score_buckets(self):
        """Test score buckets section."""
        config = create_test_config()
        
        trades = [
            create_dummy_trade('T1', 1.0, {}, 1.2),
            create_dummy_trade('T2', 1.5, {}, 1.8),
            create_dummy_trade('T3', 2.0, {}, 2.5),
            create_dummy_trade('T4', -1.0, {}, 0.8),
        ]
        
        result = BacktestResult(
            trades=trades,
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check score section
        assert 'Confluence Score Performance' in html or 'Score' in html

    def test_report_styling(self):
        """Test that report includes styling."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        # Check CSS
        assert '<style>' in html
        assert 'font-family' in html
        assert 'background-color' in html
        assert '.metric-card' in html

    def test_report_timestamp(self):
        """Test that report includes timestamp."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        html = generate_report(result, config)
        
        assert 'Generated:' in html

    def test_report_save_to_file(self, tmp_path):
        """Test saving report to file."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        output_path = tmp_path / 'test_report.html'
        
        html = generate_report(result, config, output_path=output_path)
        
        # Check file was created
        assert output_path.exists()
        
        # Check content matches
        saved_html = output_path.read_text()
        assert saved_html == html

    def test_report_with_run_id(self, tmp_path):
        """Test report generation with run_id."""
        config = create_test_config()
        
        result = BacktestResult(
            trades=[],
            equity_curve=pd.DataFrame(),
            factor_snapshots=[],
            daily_stats={},
            governance_events=[],
        )
        
        # Change to tmp_path for test
        import os
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        
        try:
            html = generate_report(result, config, run_id='test_run_123')
            
            # Check file was created in runs/test_run_123/
            expected_path = tmp_path / 'runs' / 'test_run_123' / 'report.html'
            assert expected_path.exists()
        finally:
            os.chdir(original_cwd)
