"""Tests for pre-session instrument ranking."""

import pytest
from datetime import date
from orb_confluence.analytics.pre_session_ranker import PreSessionRanker, InstrumentScore


@pytest.fixture
def ranker():
    """Create a ranker instance."""
    return PreSessionRanker(
        weight_overnight=0.25,
        weight_or_quality=0.20,
        weight_news_risk=0.15,
        weight_vol_regime=0.20,
        weight_expectancy=0.20,
        lookback_trades=20
    )


@pytest.fixture
def mock_instrument_config():
    """Create a mock instrument config."""
    class MockConfig:
        def __init__(self, symbol, adr, min_width, max_width):
            self.symbol = symbol
            self.typical_adr = adr
            self.validity_min_width_norm = min_width
            self.validity_max_width_norm = max_width
    
    return {
        'ES': MockConfig('ES', 50.0, 0.15, 0.45),
        'NQ': MockConfig('NQ', 200.0, 0.12, 0.40),
        'CL': MockConfig('CL', 3.0, 0.18, 0.50)
    }


def test_ranker_initialization():
    """Test ranker initializes correctly."""
    ranker = PreSessionRanker()
    assert ranker.weight_overnight == 0.25
    assert ranker.weight_or_quality == 0.20
    assert ranker.lookback_trades == 50
    assert len(ranker.instrument_history) == 0
    assert len(ranker.trade_history) == 0


def test_update_history(ranker):
    """Test updating instrument history."""
    ranker.update_history(
        symbol='ES',
        trading_date=date(2025, 10, 1),
        overnight_high=4500.0,
        overnight_low=4480.0,
        or_width_norm=0.25,
        session_adr=45.0
    )
    
    assert 'ES' in ranker.instrument_history
    assert len(ranker.instrument_history['ES']) == 1
    assert ranker.instrument_history['ES'][0]['or_width_norm'] == 0.25


def test_update_trade_history(ranker):
    """Test updating trade history."""
    ranker.update_trade_history(
        symbol='ES',
        trade_date=date(2025, 10, 1),
        expectancy_r=1.5,
        win=True
    )
    
    assert 'ES' in ranker.trade_history
    assert len(ranker.trade_history['ES']) == 1
    assert ranker.trade_history['ES'][0]['expectancy_r'] == 1.5
    assert ranker.trade_history['ES'][0]['win'] is True


def test_score_overnight_range_optimal(ranker):
    """Test overnight range scoring - optimal range."""
    # Optimal range: 0.3 - 0.7 of ADR
    score = ranker._score_overnight_range(0.5)
    assert score == 1.0


def test_score_overnight_range_too_quiet(ranker):
    """Test overnight range scoring - too quiet."""
    score = ranker._score_overnight_range(0.1)
    assert score == 0.3


def test_score_overnight_range_exhausted(ranker):
    """Test overnight range scoring - possibly exhausted."""
    score = ranker._score_overnight_range(1.5)
    assert score == 0.4


def test_rank_instruments_no_history(ranker, mock_instrument_config):
    """Test ranking with no historical data."""
    overnight_data = {
        'ES': (4500.0, 4480.0),  # 20 point range, 40% of ADR
        'NQ': (15500.0, 15450.0),  # 50 point range, 25% of ADR
        'CL': (70.5, 70.0)  # 0.5 point range, 16.7% of ADR
    }
    
    scores = ranker.rank_instruments(
        instruments=mock_instrument_config,
        overnight_data=overnight_data,
        trading_date=date(2025, 10, 7)
    )
    
    assert len(scores) == 3
    assert all(isinstance(s, InstrumentScore) for s in scores)
    assert scores[0].priority == 1
    assert scores[1].priority == 2
    assert scores[2].priority == 3


def test_rank_instruments_with_history(ranker, mock_instrument_config):
    """Test ranking with historical data."""
    # Add history for ES
    for i in range(20):
        ranker.update_history(
            symbol='ES',
            trading_date=date(2025, 9, i+1),
            overnight_high=4500.0 + i,
            overnight_low=4480.0 + i,
            or_width_norm=0.25,
            session_adr=50.0
        )
        
        # Add some trades
        if i % 3 == 0:
            ranker.update_trade_history(
                symbol='ES',
                trade_date=date(2025, 9, i+1),
                expectancy_r=1.2,
                win=True
            )
    
    # Add history for NQ (worse performance)
    for i in range(10):
        ranker.update_history(
            symbol='NQ',
            trading_date=date(2025, 9, i+1),
            overnight_high=15500.0 + i*10,
            overnight_low=15450.0 + i*10,
            or_width_norm=0.35,
            session_adr=200.0
        )
        
        ranker.update_trade_history(
            symbol='NQ',
            trade_date=date(2025, 9, i+1),
            expectancy_r=-0.5,
            win=False
        )
    
    overnight_data = {
        'ES': (4500.0, 4480.0),
        'NQ': (15500.0, 15450.0),
        'CL': (70.5, 70.0)
    }
    
    scores = ranker.rank_instruments(
        instruments=mock_instrument_config,
        overnight_data=overnight_data,
        trading_date=date(2025, 10, 7)
    )
    
    # ES should rank higher due to positive expectancy
    es_score = next(s for s in scores if s.symbol == 'ES')
    nq_score = next(s for s in scores if s.symbol == 'NQ')
    
    assert es_score.total_score > nq_score.total_score
    assert es_score.expectancy_score > nq_score.expectancy_score


def test_rank_instruments_with_news_risk(ranker, mock_instrument_config):
    """Test ranking with news risk penalty."""
    overnight_data = {
        'ES': (4500.0, 4480.0),
        'NQ': (15500.0, 15450.0),
        'CL': (70.5, 70.0)
    }
    
    # High news risk for CL (e.g., inventory report day)
    news_events = {
        'CL': 0.8  # High risk
    }
    
    scores = ranker.rank_instruments(
        instruments=mock_instrument_config,
        overnight_data=overnight_data,
        trading_date=date(2025, 10, 7),
        news_events=news_events
    )
    
    cl_score = next(s for s in scores if s.symbol == 'CL')
    assert cl_score.news_risk_penalty == 0.8
    # CL should be penalized in total score


def test_get_watch_list(ranker, mock_instrument_config):
    """Test watch list generation."""
    overnight_data = {
        'ES': (4500.0, 4480.0),
        'NQ': (15500.0, 15450.0),
        'CL': (70.5, 70.0)
    }
    
    scores = ranker.rank_instruments(
        instruments=mock_instrument_config,
        overnight_data=overnight_data,
        trading_date=date(2025, 10, 7)
    )
    
    watch_list = ranker.get_watch_list(scores, max_instruments=2)
    assert isinstance(watch_list, list)
    assert len(watch_list) <= 2


def test_get_recent_stats_no_history(ranker):
    """Test getting recent stats with no history."""
    stats = ranker._get_recent_stats('ES')
    assert stats['avg_or_width_norm'] == 0.5
    assert stats['win_rate'] == 0.0
    assert stats['expectancy'] == 0.0
    assert stats['trade_count'] == 0


def test_get_recent_stats_with_history(ranker):
    """Test getting recent stats with history."""
    # Add trade history
    for i in range(10):
        ranker.update_trade_history(
            symbol='ES',
            trade_date=date(2025, 9, i+1),
            expectancy_r=1.0 if i % 2 == 0 else -0.5,
            win=i % 2 == 0
        )
    
    stats = ranker._get_recent_stats('ES')
    assert stats['trade_count'] == 10
    assert stats['win_rate'] == 0.5
    assert stats['expectancy'] == 0.25  # (5*1.0 + 5*-0.5) / 10


def test_history_pruning(ranker):
    """Test that history is pruned to last 100/200 entries."""
    # Add 150 history entries
    for i in range(150):
        ranker.update_history(
            symbol='ES',
            trading_date=date(2025, 1, 1),
            overnight_high=4500.0,
            overnight_low=4480.0,
            or_width_norm=0.25,
            session_adr=50.0
        )
    
    assert len(ranker.instrument_history['ES']) == 100
    
    # Add 250 trade entries
    for i in range(250):
        ranker.update_trade_history(
            symbol='NQ',
            trade_date=date(2025, 1, 1),
            expectancy_r=1.0,
            win=True
        )
    
    assert len(ranker.trade_history['NQ']) == 200


def test_score_components_normalized(ranker, mock_instrument_config):
    """Test that all score components are normalized 0-1."""
    overnight_data = {
        'ES': (4500.0, 4480.0),
        'NQ': (15500.0, 15450.0),
        'CL': (70.5, 70.0)
    }
    
    scores = ranker.rank_instruments(
        instruments=mock_instrument_config,
        overnight_data=overnight_data,
        trading_date=date(2025, 10, 7)
    )
    
    for score in scores:
        assert 0.0 <= score.overnight_range_score <= 1.0
        assert 0.0 <= score.or_quality_score <= 1.0
        assert 0.0 <= score.news_risk_penalty <= 1.0
        assert 0.0 <= score.vol_regime_score <= 1.0
        assert 0.0 <= score.expectancy_score <= 1.0
        assert 0.0 <= score.total_score <= 1.0


def test_reason_generation(ranker):
    """Test reason string generation."""
    reason = ranker._generate_reason(
        overnight_score=0.9,
        or_quality_score=0.85,
        news_risk_penalty=0.1,
        vol_regime_score=0.82,
        expectancy_score=0.75
    )
    
    assert isinstance(reason, str)
    assert "optimal overnight range" in reason
    assert "good historical OR quality" in reason
    assert "consistent volatility" in reason
    assert "strong recent performance" in reason
