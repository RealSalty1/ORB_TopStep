"""Tests for daily R loss cap governance feature."""

from datetime import datetime, time

import pytest

from orb_confluence.strategy.governance import GovernanceManager


class TestDailyLossCap:
    """Tests for max_daily_loss_r feature."""
    
    def test_no_loss_cap_by_default(self):
        """Test that loss cap is None by default (no limit)."""
        gov = GovernanceManager(
            max_signals_per_day=5,
            lockout_after_losses=3,
            max_daily_loss_r=None,
        )
        
        # Can lose any amount without lockout (only consecutive losses matter)
        gov.register_trade_outcome(win=False, realized_r=-2.0, full_stop_loss=True)
        assert not gov.state.lockout_active
        
        gov.register_trade_outcome(win=False, realized_r=-3.0, full_stop_loss=True)
        assert not gov.state.lockout_active
        
        # Third loss triggers consecutive loss lockout
        gov.register_trade_outcome(win=False, realized_r=-2.0, full_stop_loss=True)
        assert gov.state.lockout_active
        assert "Consecutive losses" in gov.state.lockout_reason
    
    def test_loss_cap_triggers_lockout(self):
        """Test that reaching daily loss cap triggers lockout."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,  # High threshold
            max_daily_loss_r=5.0,     # Cap at -5R
        )
        
        # Lose 2R
        gov.register_trade_outcome(win=False, realized_r=-2.0)
        assert gov.state.daily_realized_r == -2.0
        assert not gov.state.lockout_active
        
        # Lose another 2R (total -4R)
        gov.register_trade_outcome(win=False, realized_r=-2.0)
        assert gov.state.daily_realized_r == -4.0
        assert not gov.state.lockout_active
        
        # Lose another 1.5R (total -5.5R, exceeds cap)
        gov.register_trade_outcome(win=False, realized_r=-1.5)
        assert gov.state.daily_realized_r == -5.5
        assert gov.state.lockout_active
        assert "Daily loss cap" in gov.state.lockout_reason
    
    def test_loss_cap_exact_boundary(self):
        """Test lockout at exact boundary."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,
            max_daily_loss_r=5.0,
        )
        
        # Lose exactly 5R
        gov.register_trade_outcome(win=False, realized_r=-5.0)
        assert gov.state.daily_realized_r == -5.0
        assert gov.state.lockout_active
        assert "Daily loss cap" in gov.state.lockout_reason
    
    def test_loss_cap_with_mixed_outcomes(self):
        """Test loss cap with mixed wins and losses."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,
            max_daily_loss_r=3.0,
        )
        
        # Win 2R
        gov.register_trade_outcome(win=True, realized_r=2.0)
        assert gov.state.daily_realized_r == 2.0
        assert not gov.state.lockout_active
        
        # Lose 3R (net -1R)
        gov.register_trade_outcome(win=False, realized_r=-3.0)
        assert gov.state.daily_realized_r == -1.0
        assert not gov.state.lockout_active
        
        # Win 1R (net 0R)
        gov.register_trade_outcome(win=True, realized_r=1.0)
        assert gov.state.daily_realized_r == 0.0
        assert not gov.state.lockout_active
        
        # Lose 3.5R (net -3.5R, exceeds cap)
        gov.register_trade_outcome(win=False, realized_r=-3.5)
        assert gov.state.daily_realized_r == -3.5
        assert gov.state.lockout_active
    
    def test_loss_cap_resets_on_new_day(self):
        """Test that loss cap counter resets on new day."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,
            max_daily_loss_r=5.0,
        )
        
        # Day 1: Lose 5R and get locked out
        gov.register_trade_outcome(win=False, realized_r=-5.0)
        assert gov.state.daily_realized_r == -5.0
        assert gov.state.lockout_active
        
        # New day reset
        gov.new_day_reset(datetime(2024, 1, 3).date())
        assert gov.state.daily_realized_r == 0.0
        assert not gov.state.lockout_active
        
        # Can trade again
        assert gov.can_emit_signal(datetime(2024, 1, 3, 10, 0))
    
    def test_loss_cap_with_profitable_day(self):
        """Test that profitable day never triggers loss cap."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,
            max_daily_loss_r=3.0,
        )
        
        # Profitable trades
        gov.register_trade_outcome(win=True, realized_r=5.0)
        gov.register_trade_outcome(win=True, realized_r=3.0)
        gov.register_trade_outcome(win=True, realized_r=2.0)
        
        assert gov.state.daily_realized_r == 10.0
        assert not gov.state.lockout_active
    
    def test_loss_cap_precedence_over_consecutive_losses(self):
        """Test that loss cap can trigger before consecutive loss lockout."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=3,   # 3 consecutive losses
            max_daily_loss_r=4.0,     # 4R loss cap
        )
        
        # First loss: 2.5R (not full stop, no consecutive penalty)
        gov.register_trade_outcome(win=False, realized_r=-2.5, full_stop_loss=False)
        assert gov.state.consecutive_losses == 0
        assert not gov.state.lockout_active
        
        # Second loss: 2R (exceeds cap, locks out)
        gov.register_trade_outcome(win=False, realized_r=-2.0, full_stop_loss=False)
        assert gov.state.daily_realized_r == -4.5
        assert gov.state.lockout_active
        assert "Daily loss cap" in gov.state.lockout_reason
        
        # Consecutive losses never reached 3
        assert gov.state.consecutive_losses == 0
    
    def test_stats_include_daily_r(self):
        """Test that get_stats includes daily_realized_r."""
        gov = GovernanceManager(
            max_signals_per_day=5,
            lockout_after_losses=2,
            max_daily_loss_r=3.0,
        )
        
        gov.register_trade_outcome(win=True, realized_r=1.5)
        gov.register_trade_outcome(win=False, realized_r=-0.8)
        
        stats = gov.get_stats()
        assert 'daily_realized_r' in stats
        assert stats['daily_realized_r'] == pytest.approx(0.7, rel=1e-6)


class TestLossCapIntegration:
    """Integration tests for loss cap with other governance rules."""
    
    def test_loss_cap_blocks_signal_emission(self):
        """Test that loss cap lockout blocks new signals."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=10,
            max_daily_loss_r=3.0,
        )
        
        current_time = datetime(2024, 1, 2, 10, 30)
        
        # Initially can emit
        assert gov.can_emit_signal(current_time)
        
        # Lose 3.5R
        gov.register_trade_outcome(win=False, realized_r=-3.5)
        
        # Now locked out
        assert not gov.can_emit_signal(current_time)
    
    def test_multiple_lockout_conditions(self):
        """Test handling of multiple lockout conditions."""
        gov = GovernanceManager(
            max_signals_per_day=10,
            lockout_after_losses=2,
            max_daily_loss_r=10.0,  # High cap
        )
        
        # Trigger consecutive loss lockout first
        gov.register_trade_outcome(win=False, realized_r=-1.0, full_stop_loss=True)
        gov.register_trade_outcome(win=False, realized_r=-1.0, full_stop_loss=True)
        
        assert gov.state.lockout_active
        assert "Consecutive losses" in gov.state.lockout_reason
        
        # Even though we're already locked out, registering more losses updates daily R
        gov.register_trade_outcome(win=False, realized_r=-1.0, full_stop_loss=True)
        assert gov.state.daily_realized_r == -3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
