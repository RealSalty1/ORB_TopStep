"""Tests for trade manager."""

from datetime import datetime

import pandas as pd
import pytest

from orb_confluence.strategy.trade_state import ActiveTrade, PartialFill
from orb_confluence.strategy.trade_manager import TradeManager, TradeEvent


class TestTradeManager:
    """Test TradeManager class."""

    def test_partial_fill_long(self):
        """Test partial fill for long trade."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 0.5), (102.0, 0.5)],
        )

        manager = TradeManager()

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 100.5,
            'high': 101.5,  # Hits T1
            'low': 100.3,
            'close': 101.2,
        })

        update = manager.update(trade, bar)

        assert TradeEvent.PARTIAL_FILL in update.events
        assert len(update.trade.partials_filled) == 1
        assert update.trade.remaining_size == pytest.approx(0.5, rel=0.01)
        assert not update.closed

    def test_all_targets_filled(self):
        """Test trade closed when all targets filled."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 0.5), (102.0, 0.5)],
        )

        manager = TradeManager()

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 100.5,
            'high': 102.5,  # Hits all targets
            'low': 100.3,
            'close': 102.2,
        })

        update = manager.update(trade, bar)

        assert TradeEvent.PARTIAL_FILL in update.events
        assert TradeEvent.TARGET_HIT in update.events
        assert len(update.trade.partials_filled) == 2
        assert update.trade.remaining_size <= 0.001
        assert update.closed
        assert update.trade.exit_reason == 'all_targets'

    def test_stop_hit_long(self):
        """Test stop hit for long trade."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 1.0)],
        )

        manager = TradeManager()

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 99.5,
            'high': 99.8,
            'low': 98.5,  # Hits stop
            'close': 99.2,
        })

        update = manager.update(trade, bar)

        assert TradeEvent.STOP_HIT in update.events
        assert update.closed
        assert update.trade.exit_reason == 'stop'
        assert update.trade.exit_price == 99.0

    def test_stop_hit_short(self):
        """Test stop hit for short trade."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='short',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=101.0,
            stop_price_current=101.0,
            targets=[(99.0, 1.0)],
        )

        manager = TradeManager()

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 100.5,
            'high': 101.5,  # Hits stop
            'low': 100.2,
            'close': 100.8,
        })

        update = manager.update(trade, bar)

        assert TradeEvent.STOP_HIT in update.events
        assert update.closed

    def test_conservative_fills_stop_precedence(self):
        """Test conservative fills: stop precedence when both hit."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 1.0)],
        )

        manager = TradeManager(conservative_fills=True)

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 100.0,
            'high': 101.5,  # Hits target
            'low': 98.5,  # Hits stop
            'close': 100.2,
        })

        update = manager.update(trade, bar)

        # Should close on stop (conservative)
        assert TradeEvent.STOP_HIT in update.events
        assert update.closed
        assert update.trade.exit_reason == 'stop'

    def test_breakeven_move(self):
        """Test breakeven stop adjustment."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 0.5), (102.0, 0.5)],
        )

        manager = TradeManager(move_be_at_r=1.0, be_buffer=0.05)

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'open': 100.5,
            'high': 101.5,  # 1.5R, triggers BE
            'low': 100.3,
            'close': 101.2,
        })

        update = manager.update(trade, bar)

        assert TradeEvent.BREAKEVEN_MOVE in update.events
        assert update.trade.moved_to_breakeven is True
        assert update.trade.stop_price_current == pytest.approx(100.05, rel=0.001)

    def test_partial_then_stop(self):
        """Test partial fill followed by stop on next bar."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 0.5), (102.0, 0.5)],
        )

        manager = TradeManager()

        # Bar 1: Hit T1
        bar1 = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'high': 101.5,
            'low': 100.3,
        })

        update1 = manager.update(trade, bar1)
        assert TradeEvent.PARTIAL_FILL in update1.events
        assert not update1.closed

        # Bar 2: Hit stop
        bar2 = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 6),
            'high': 100.5,
            'low': 98.5,  # Hits stop
        })

        update2 = manager.update(trade, bar2)
        assert TradeEvent.STOP_HIT in update2.events
        assert update2.closed

        # Should have 1 partial + stop exit
        assert len(update2.trade.partials_filled) == 1

    def test_r_tracking(self):
        """Test R-multiple tracking (max favorable/adverse)."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(102.0, 1.0)],
        )

        manager = TradeManager()

        # Bar 1: Go up (favorable)
        bar1 = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 5),
            'high': 101.5,  # 1.5R
            'low': 100.2,
        })

        manager.update(trade, bar1)
        assert trade.max_favorable_r == pytest.approx(1.5, rel=0.01)

        # Bar 2: Pull back (adverse)
        bar2 = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 6),
            'high': 100.5,
            'low': 99.5,  # -0.5R
        })

        manager.update(trade, bar2)
        assert trade.max_adverse_r == pytest.approx(-0.5, rel=0.01)

    def test_no_update_after_close(self):
        """Test that closed trade can't be updated."""
        trade = ActiveTrade(
            trade_id='TEST_1',
            direction='long',
            entry_timestamp=datetime(2024, 1, 2, 15, 0),
            entry_price=100.0,
            stop_price_initial=99.0,
            stop_price_current=99.0,
            targets=[(101.0, 1.0)],
            exit_timestamp=datetime(2024, 1, 2, 15, 10),  # Already closed
        )

        manager = TradeManager()

        bar = pd.Series({
            'timestamp_utc': datetime(2024, 1, 2, 15, 15),
            'high': 102.0,
            'low': 101.0,
        })

        update = manager.update(trade, bar)

        assert len(update.events) == 0
        assert update.closed is True
