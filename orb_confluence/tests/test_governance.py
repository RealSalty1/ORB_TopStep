"""Tests for governance rules."""

from datetime import datetime, time, timedelta

import pytest

from orb_confluence.strategy.governance import GovernanceManager, GovernanceState


class TestGovernanceState:
    """Test GovernanceState dataclass."""

    def test_initialization(self):
        """Test state initialization."""
        state = GovernanceState()

        assert state.current_date is None
        assert state.day_signal_count == 0
        assert state.consecutive_losses == 0
        assert state.lockout_active is False
        assert state.lockout_reason is None
        assert state.trade_outcomes == []

    def test_repr(self):
        """Test string representation."""
        state = GovernanceState(
            current_date=datetime(2024, 1, 2).date(),
            day_signal_count=2,
            consecutive_losses=1,
        )

        repr_str = repr(state)
        assert "2024-01-02" in repr_str
        assert "signals=2" in repr_str
        assert "losses=1" in repr_str


class TestGovernanceManager:
    """Test GovernanceManager class."""

    def test_initialization(self):
        """Test manager initialization."""
        gov = GovernanceManager(
            max_signals_per_day=3,
            lockout_after_losses=2,
            time_cutoff=time(15, 30),
        )

        assert gov.max_signals_per_day == 3
        assert gov.lockout_after_losses == 2
        assert gov.time_cutoff == time(15, 30)
        assert gov.state.day_signal_count == 0

    def test_new_day_reset(self):
        """Test new day reset."""
        gov = GovernanceManager()

        # Set some state
        gov.state.day_signal_count = 3
        gov.state.consecutive_losses = 1
        gov.state.lockout_active = True

        # Reset
        new_date = datetime(2024, 1, 3).date()
        gov.new_day_reset(new_date)

        assert gov.state.current_date == new_date
        assert gov.state.day_signal_count == 0
        assert gov.state.lockout_active is False
        # Consecutive losses persist across days
        assert gov.state.consecutive_losses == 1

    def test_new_session_reset(self):
        """Test new session reset (full reset)."""
        gov = GovernanceManager()

        # Set some state
        gov.state.day_signal_count = 3
        gov.state.consecutive_losses = 2
        gov.state.lockout_active = True

        # Reset
        new_date = datetime(2024, 1, 3).date()
        gov.new_session_reset(new_date)

        assert gov.state.current_date == new_date
        assert gov.state.day_signal_count == 0
        assert gov.state.consecutive_losses == 0  # Cleared in session reset
        assert gov.state.lockout_active is False

    def test_register_signal_emitted(self):
        """Test signal emission registration."""
        gov = GovernanceManager()

        ts1 = datetime(2024, 1, 2, 10, 0)
        gov.register_signal_emitted(ts1)

        assert gov.state.day_signal_count == 1
        assert gov.state.current_date == ts1.date()

        # Same day
        ts2 = datetime(2024, 1, 2, 11, 0)
        gov.register_signal_emitted(ts2)

        assert gov.state.day_signal_count == 2

    def test_register_signal_emitted_new_day(self):
        """Test signal emission on new day auto-resets."""
        gov = GovernanceManager()

        ts1 = datetime(2024, 1, 2, 10, 0)
        gov.register_signal_emitted(ts1)
        assert gov.state.day_signal_count == 1

        # New day
        ts2 = datetime(2024, 1, 3, 10, 0)
        gov.register_signal_emitted(ts2)

        assert gov.state.day_signal_count == 1  # Reset
        assert gov.state.current_date == ts2.date()

    def test_register_trade_outcome_win(self):
        """Test registering winning trade."""
        gov = GovernanceManager()

        gov.state.consecutive_losses = 2

        gov.register_trade_outcome(win=True)

        assert gov.state.consecutive_losses == 0  # Reset on win
        assert len(gov.state.trade_outcomes) == 1
        assert gov.state.trade_outcomes[0] is True

    def test_register_trade_outcome_loss(self):
        """Test registering losing trade (not full stop)."""
        gov = GovernanceManager()

        gov.register_trade_outcome(win=False, full_stop_loss=False)

        assert gov.state.consecutive_losses == 0  # No penalty for partial exit
        assert len(gov.state.trade_outcomes) == 1
        assert gov.state.trade_outcomes[0] is False

    def test_register_trade_outcome_full_stop(self):
        """Test registering full stop loss."""
        gov = GovernanceManager(lockout_after_losses=2)

        gov.register_trade_outcome(win=False, full_stop_loss=True)

        assert gov.state.consecutive_losses == 1
        assert not gov.state.lockout_active  # Not yet

    def test_lockout_after_consecutive_losses(self):
        """Test lockout activates after N consecutive losses."""
        gov = GovernanceManager(lockout_after_losses=2)

        # First loss
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.consecutive_losses == 1
        assert not gov.state.lockout_active

        # Second loss (triggers lockout)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.consecutive_losses == 2
        assert gov.state.lockout_active is True
        assert "Consecutive losses" in gov.state.lockout_reason

    def test_lockout_prevents_signals(self):
        """Test that lockout prevents signal emission."""
        gov = GovernanceManager(lockout_after_losses=2)

        # Trigger lockout
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)

        assert gov.state.lockout_active

        # Try to emit signal
        current_time = datetime(2024, 1, 2, 10, 0)
        can_emit = gov.can_emit_signal(current_time)

        assert can_emit is False

    def test_lockout_resets_next_session(self):
        """Test that lockout clears on new session reset."""
        gov = GovernanceManager(lockout_after_losses=2)

        # Trigger lockout
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.lockout_active

        # New session (full reset)
        new_date = datetime(2024, 1, 3).date()
        gov.new_session_reset(new_date)

        assert not gov.state.lockout_active
        assert gov.state.consecutive_losses == 0

    def test_lockout_persists_across_day_reset(self):
        """Test that lockout status is cleared on new day reset."""
        gov = GovernanceManager(lockout_after_losses=2)

        # Trigger lockout
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.lockout_active

        # New day (not full session reset)
        new_date = datetime(2024, 1, 3).date()
        gov.new_day_reset(new_date)

        # Lockout flag cleared, but consecutive losses persist
        assert not gov.state.lockout_active
        assert gov.state.consecutive_losses == 2

    def test_can_emit_signal_basic(self):
        """Test basic signal emission check."""
        gov = GovernanceManager(max_signals_per_day=3)

        current_time = datetime(2024, 1, 2, 10, 0)
        assert gov.can_emit_signal(current_time) is True

    def test_can_emit_signal_daily_cap(self):
        """Test daily signal cap enforcement."""
        gov = GovernanceManager(max_signals_per_day=2)

        current_time = datetime(2024, 1, 2, 10, 0)

        # Emit 2 signals
        gov.register_signal_emitted(current_time)
        gov.register_signal_emitted(current_time)

        # Try third
        assert gov.can_emit_signal(current_time) is False

    def test_can_emit_signal_time_cutoff(self):
        """Test time cutoff enforcement."""
        gov = GovernanceManager(time_cutoff=time(15, 0))

        # Before cutoff
        before = datetime(2024, 1, 2, 14, 59)
        assert gov.can_emit_signal(before) is True

        # At cutoff
        at = datetime(2024, 1, 2, 15, 0)
        assert gov.can_emit_signal(at) is False

        # After cutoff
        after = datetime(2024, 1, 2, 15, 30)
        assert gov.can_emit_signal(after) is False

    def test_reset_consecutive_losses(self):
        """Test manual reset of consecutive losses."""
        gov = GovernanceManager(lockout_after_losses=2)

        # Build up losses
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)

        assert gov.state.consecutive_losses == 2
        assert gov.state.lockout_active

        # Manual reset
        gov.reset_consecutive_losses()

        assert gov.state.consecutive_losses == 0
        assert not gov.state.lockout_active

    def test_get_stats(self):
        """Test governance statistics."""
        gov = GovernanceManager()

        date = datetime(2024, 1, 2).date()
        gov.new_day_reset(date)

        gov.register_signal_emitted(datetime(2024, 1, 2, 10, 0))
        gov.register_trade_outcome(win=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)

        stats = gov.get_stats()

        assert stats['current_date'] == date
        assert stats['day_signal_count'] == 1
        assert stats['consecutive_losses'] == 1
        assert stats['total_trades_today'] == 2
        assert stats['wins_today'] == 1
        assert stats['losses_today'] == 1

    def test_win_resets_consecutive_losses(self):
        """Test that winning trade resets consecutive loss counter."""
        gov = GovernanceManager(lockout_after_losses=3)

        # Two losses
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.consecutive_losses == 2

        # Win resets
        gov.register_trade_outcome(win=True)
        assert gov.state.consecutive_losses == 0

        # Two more losses (no lockout since reset)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        gov.register_trade_outcome(win=False, full_stop_loss=True)
        assert gov.state.consecutive_losses == 2
        assert not gov.state.lockout_active  # Need 3 for lockout

    def test_scenario_full_trading_day(self):
        """Test realistic full trading day scenario."""
        gov = GovernanceManager(
            max_signals_per_day=3,
            lockout_after_losses=2,
            time_cutoff=time(15, 30),
        )

        date = datetime(2024, 1, 2).date()

        # Signal 1: 10:00 - Can emit
        ts1 = datetime(2024, 1, 2, 10, 0)
        assert gov.can_emit_signal(ts1)
        gov.register_signal_emitted(ts1)
        gov.register_trade_outcome(win=False, full_stop_loss=True)

        # Signal 2: 11:00 - Can emit
        ts2 = datetime(2024, 1, 2, 11, 0)
        assert gov.can_emit_signal(ts2)
        gov.register_signal_emitted(ts2)
        gov.register_trade_outcome(win=False, full_stop_loss=True)

        # Now locked out after 2 consecutive losses
        assert gov.state.lockout_active

        # Signal 3: 12:00 - Blocked by lockout
        ts3 = datetime(2024, 1, 2, 12, 0)
        assert not gov.can_emit_signal(ts3)

        # Next day: New session reset
        gov.new_session_reset(datetime(2024, 1, 3).date())

        # Signal 4: 10:00 next day - Can emit again
        ts4 = datetime(2024, 1, 3, 10, 0)
        assert gov.can_emit_signal(ts4)
        gov.register_signal_emitted(ts4)
        gov.register_trade_outcome(win=True)  # Win resets losses

        assert gov.state.consecutive_losses == 0
        assert not gov.state.lockout_active