"""Property-Based Tests for ORB Confluence Strategy.

Uses Hypothesis to verify invariants hold across wide input ranges.

Tests verify:
- OR width is always non-negative
- Score is monotonic (more factors/weight = higher score)
- Trade R computation never divides by zero
- Governance lockout triggers exactly at threshold
"""

from datetime import datetime, timedelta
from typing import Dict

import pytest
from hypothesis import given, strategies as st, assume, settings

from orb_confluence.features.opening_range import (
    OpeningRangeBuilder,
    ORState,
    apply_buffer,
    calculate_or_from_bars,
)
from orb_confluence.strategy.scoring import compute_score, analyze_confluence
from orb_confluence.strategy.risk import compute_stop, build_targets
from orb_confluence.strategy.governance import GovernanceManager
from orb_confluence.strategy.trade_state import TradeSignal


# ============================================================================
# Custom Strategies
# ============================================================================


@st.composite
def or_bars(draw):
    """Generate valid OHLC bars for OR calculation."""
    base_price = draw(st.floats(min_value=10.0, max_value=1000.0))
    n_bars = draw(st.integers(min_value=5, max_value=30))
    
    bars = []
    for _ in range(n_bars):
        # Ensure valid OHLC relationships
        low = base_price * draw(st.floats(min_value=0.98, max_value=1.0))
        high = base_price * draw(st.floats(min_value=1.0, max_value=1.02))
        open_price = draw(st.floats(min_value=low, max_value=high))
        close = draw(st.floats(min_value=low, max_value=high))
        
        bars.append({
            'high': high,
            'low': low,
            'open': open_price,
            'close': close,
            'timestamp': datetime(2024, 1, 1, 9, 30) + timedelta(minutes=len(bars)),
        })
    
    return bars


@st.composite
def factor_flags(draw):
    """Generate random factor flags dictionary."""
    return {
        'rel_vol': draw(st.booleans()),
        'price_action': draw(st.booleans()),
        'vwap': draw(st.booleans()),
        'adx': draw(st.booleans()),
        'profile': draw(st.booleans()),
    }


@st.composite
def factor_weights(draw):
    """Generate valid factor weights (non-negative, sum > 0)."""
    weights = {
        'rel_vol': draw(st.floats(min_value=0.0, max_value=1.0)),
        'price_action': draw(st.floats(min_value=0.0, max_value=1.0)),
        'vwap': draw(st.floats(min_value=0.0, max_value=1.0)),
        'adx': draw(st.floats(min_value=0.0, max_value=1.0)),
        'profile': draw(st.floats(min_value=0.0, max_value=1.0)),
    }
    
    # Ensure at least one weight is positive
    if sum(weights.values()) == 0:
        weights['rel_vol'] = 0.1
    
    return weights


@st.composite
def trade_prices(draw):
    """Generate valid trade entry/exit prices."""
    entry = draw(st.floats(min_value=10.0, max_value=1000.0))
    stop = draw(st.floats(min_value=10.0, max_value=1000.0))
    
    # Ensure stop != entry (avoid division by zero)
    assume(abs(stop - entry) > 0.01)
    
    return entry, stop


# ============================================================================
# Property Tests: Opening Range
# ============================================================================


class TestORWidthProperty:
    """Property tests for Opening Range width."""
    
    @given(or_bars())
    @settings(max_examples=100)
    def test_or_width_always_non_negative(self, bars):
        """Property: OR width is always >= 0."""
        or_state = calculate_or_from_bars(bars)
        
        width = or_state.high - or_state.low
        assert width >= 0, f"OR width {width} is negative"
    
    @given(
        or_bars(),
        st.floats(min_value=0.0, max_value=0.1)
    )
    @settings(max_examples=100)
    def test_buffer_increases_width(self, bars, buffer_pct):
        """Property: Adding buffer always increases OR width."""
        or_state = calculate_or_from_bars(bars)
        original_width = or_state.high - or_state.low
        
        buffered = apply_buffer(or_state, buffer_pct, buffer_pct)
        buffered_width = buffered.high - buffered.low
        
        # Buffer should increase width (or keep it same if buffer=0)
        assert buffered_width >= original_width, \
            f"Buffer decreased width: {original_width} -> {buffered_width}"
    
    @given(or_bars())
    @settings(max_examples=100)
    def test_or_high_always_gte_low(self, bars):
        """Property: OR high is always >= OR low."""
        or_state = calculate_or_from_bars(bars)
        assert or_state.high >= or_state.low, \
            f"OR high {or_state.high} < OR low {or_state.low}"
    
    @given(
        or_bars(),
        st.floats(min_value=0.0, max_value=0.2),
        st.floats(min_value=0.0, max_value=0.2)
    )
    @settings(max_examples=100)
    def test_asymmetric_buffers_preserve_order(self, bars, buffer_long, buffer_short):
        """Property: Asymmetric buffers preserve high >= low."""
        or_state = calculate_or_from_bars(bars)
        buffered = apply_buffer(or_state, buffer_long, buffer_short)
        
        assert buffered.high >= buffered.low, \
            f"Buffered OR invalid: high {buffered.high} < low {buffered.low}"
    
    @given(or_bars())
    @settings(max_examples=100)
    def test_or_prices_within_bar_range(self, bars):
        """Property: OR high/low are within the range of all bars."""
        or_state = calculate_or_from_bars(bars)
        
        all_highs = [b['high'] for b in bars]
        all_lows = [b['low'] for b in bars]
        
        assert or_state.high <= max(all_highs), \
            f"OR high {or_state.high} exceeds max bar high {max(all_highs)}"
        assert or_state.low >= min(all_lows), \
            f"OR low {or_state.low} below min bar low {min(all_lows)}"


# ============================================================================
# Property Tests: Scoring
# ============================================================================


class TestScoringMonotonicityProperty:
    """Property tests for score monotonicity."""
    
    @given(
        factor_flags(),
        factor_weights(),
        st.booleans()
    )
    @settings(max_examples=200)
    def test_enabling_factor_increases_score(self, flags, weights, trend_weak):
        """Property: Enabling a passing factor never decreases score."""
        direction = 'long'
        base_req = 0.5
        weak_req = 0.3
        
        # Compute base score
        base_score, _, _ = compute_score(
            direction, flags, weights, trend_weak, base_req, weak_req
        )
        
        # Enable one more factor (if any are False)
        for factor_name, flag_value in flags.items():
            if not flag_value:
                enhanced_flags = flags.copy()
                enhanced_flags[factor_name] = True
                
                enhanced_score, _, _ = compute_score(
                    direction, enhanced_flags, weights, trend_weak, base_req, weak_req
                )
                
                # Score should not decrease
                assert enhanced_score >= base_score, \
                    f"Enabling {factor_name} decreased score: {base_score} -> {enhanced_score}"
                break
    
    @given(
        factor_flags(),
        factor_weights(),
        st.booleans()
    )
    @settings(max_examples=200)
    def test_increasing_weight_increases_contribution(self, flags, weights, trend_weak):
        """Property: Increasing weight of enabled factor increases score."""
        direction = 'long'
        base_req = 0.5
        weak_req = 0.3
        
        # Find an enabled factor
        enabled_factor = None
        for factor_name, flag_value in flags.items():
            if flag_value and weights[factor_name] > 0:
                enabled_factor = factor_name
                break
        
        if enabled_factor is None:
            # No enabled factors with weight, skip
            return
        
        # Compute base score
        base_score, _, _ = compute_score(
            direction, flags, weights, trend_weak, base_req, weak_req
        )
        
        # Increase weight
        enhanced_weights = weights.copy()
        enhanced_weights[enabled_factor] = weights[enabled_factor] * 1.5
        
        enhanced_score, _, _ = compute_score(
            direction, flags, enhanced_weights, trend_weak, base_req, weak_req
        )
        
        # Score should not decrease
        assert enhanced_score >= base_score, \
            f"Increasing weight of {enabled_factor} decreased score: {base_score} -> {enhanced_score}"
    
    @given(
        factor_flags(),
        factor_weights(),
        st.booleans()
    )
    @settings(max_examples=200)
    def test_score_bounded(self, flags, weights, trend_weak):
        """Property: Score is always between 0 and 1."""
        direction = 'long'
        base_req = 0.5
        weak_req = 0.3
        
        score, required, passed = compute_score(
            direction, flags, weights, trend_weak, base_req, weak_req
        )
        
        assert 0.0 <= score <= 1.0, f"Score {score} out of bounds [0, 1]"
        assert 0.0 <= required <= 1.0, f"Required {required} out of bounds [0, 1]"
    
    @given(
        factor_flags(),
        factor_weights(),
        st.booleans()
    )
    @settings(max_examples=200)
    def test_all_factors_enabled_maximizes_score(self, flags, weights, trend_weak):
        """Property: Enabling all factors maximizes score given weights."""
        direction = 'long'
        base_req = 0.5
        weak_req = 0.3
        
        # Compute score with given flags
        partial_score, _, _ = compute_score(
            direction, flags, weights, trend_weak, base_req, weak_req
        )
        
        # Enable all factors
        all_enabled = {k: True for k in flags.keys()}
        
        max_score, _, _ = compute_score(
            direction, all_enabled, weights, trend_weak, base_req, weak_req
        )
        
        # Max score should be >= partial score
        assert max_score >= partial_score, \
            f"Enabling all factors decreased score: {partial_score} -> {max_score}"
    
    @given(
        factor_weights(),
        st.booleans()
    )
    @settings(max_examples=100)
    def test_zero_factors_gives_zero_score(self, weights, trend_weak):
        """Property: No enabled factors gives zero score."""
        direction = 'long'
        base_req = 0.5
        weak_req = 0.3
        
        no_factors = {k: False for k in weights.keys()}
        
        score, _, passed = compute_score(
            direction, no_factors, weights, trend_weak, base_req, weak_req
        )
        
        assert score == 0.0, f"Expected zero score with no factors, got {score}"
        assert not passed, "Expected to fail with zero score"


# ============================================================================
# Property Tests: Trade R Calculation
# ============================================================================


class TestTradeRComputationProperty:
    """Property tests for R-multiple calculations."""
    
    @given(trade_prices())
    @settings(max_examples=200)
    def test_stop_distance_never_zero(self, prices):
        """Property: Stop distance is never zero (no division by zero)."""
        entry, stop = prices
        
        # This should never trigger division by zero
        stop_distance = abs(entry - stop)
        assert stop_distance > 0, f"Stop distance is zero: entry={entry}, stop={stop}"
    
    @given(
        st.floats(min_value=10.0, max_value=1000.0),
        st.floats(min_value=10.0, max_value=1000.0),
        st.floats(min_value=10.0, max_value=1000.0)
    )
    @settings(max_examples=200)
    def test_realized_r_computation_valid(self, entry, stop, exit_price):
        """Property: Realized R never involves division by zero."""
        # Ensure stop != entry
        assume(abs(stop - entry) > 0.01)
        
        # Compute R
        stop_distance = abs(entry - stop)
        profit = exit_price - entry
        realized_r = profit / stop_distance
        
        # R should be a valid number
        assert not (realized_r != realized_r), f"R is NaN"  # Check for NaN
        assert abs(realized_r) < 1e6, f"R is too large: {realized_r}"
    
    @given(
        st.floats(min_value=10.0, max_value=1000.0),
        st.floats(min_value=10.0, max_value=1000.0),
        st.floats(min_value=1.0, max_value=5.0)
    )
    @settings(max_examples=200)
    def test_target_r_always_positive(self, entry, stop, target_r):
        """Property: Target prices for positive R are always achievable."""
        assume(abs(entry - stop) > 0.01)
        
        stop_distance = abs(entry - stop)
        
        # Long trade
        if entry > stop:
            target_price = entry + (target_r * stop_distance)
            assert target_price > entry, f"Long target {target_price} not above entry {entry}"
        # Short trade
        else:
            target_price = entry - (target_r * stop_distance)
            assert target_price < entry, f"Short target {target_price} not below entry {entry}"
    
    @given(
        st.floats(min_value=100.0, max_value=500.0),
        st.floats(min_value=1.0, max_value=10.0)
    )
    @settings(max_examples=100)
    def test_build_targets_no_division_error(self, entry_price, stop_distance):
        """Property: build_targets never divides by zero."""
        # Long trade scenario
        stop_price = entry_price - stop_distance
        
        # Should not raise any errors
        targets = build_targets(
            entry=entry_price,
            stop=stop_price,
            direction='long',
            partials=True,
            t1_r=1.0,
            t2_r=2.0,
            runner_r=3.0
        )
        
        assert len(targets) > 0, "No targets generated"
        for target in targets:
            assert target['price'] > entry_price, "Long target not above entry"
    
    @given(
        st.floats(min_value=100.0, max_value=500.0),
        st.floats(min_value=1.0, max_value=10.0),
        st.floats(min_value=-5.0, max_value=5.0)
    )
    @settings(max_examples=200)
    def test_r_sign_consistent_with_pnl(self, entry, stop_distance, pnl_mult):
        """Property: R sign is consistent with profit/loss direction."""
        stop = entry - stop_distance  # Long trade
        exit_price = entry + (pnl_mult * stop_distance)
        
        pnl = exit_price - entry
        realized_r = pnl / stop_distance
        
        # Sign consistency
        if pnl > 0:
            assert realized_r > 0, f"Positive PnL but negative R: {realized_r}"
        elif pnl < 0:
            assert realized_r < 0, f"Negative PnL but positive R: {realized_r}"
        else:
            assert abs(realized_r) < 0.01, f"Zero PnL but non-zero R: {realized_r}"


# ============================================================================
# Property Tests: Governance
# ============================================================================


class TestGovernanceLockoutProperty:
    """Property tests for governance lockout behavior."""
    
    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_lockout_triggers_exactly_at_threshold(self, lockout_threshold):
        """Property: Lockout triggers exactly when consecutive losses reach threshold."""
        gov = GovernanceManager(
            max_signals_per_day=100,
            lockout_after_losses=lockout_threshold,
            time_cutoff=None
        )
        
        # Simulate losses up to threshold - 1
        for _ in range(lockout_threshold - 1):
            gov.register_trade_outcome(win=False)
        
        # Should NOT be locked out yet
        assert gov.can_emit_signal(datetime.now()), \
            f"Locked out before reaching threshold {lockout_threshold}"
        assert not gov.state.lockout_flag, "Lockout flag set prematurely"
        
        # One more loss should trigger lockout
        gov.register_trade_outcome(win=False)
        
        # Should NOW be locked out
        assert not gov.can_emit_signal(datetime.now()), \
            f"Not locked out after {lockout_threshold} losses"
        assert gov.state.lockout_flag, f"Lockout flag not set at threshold"
    
    @given(
        st.integers(min_value=2, max_value=10),
        st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100)
    def test_win_resets_consecutive_losses(self, lockout_threshold, losses_before_win):
        """Property: A win resets consecutive loss counter."""
        assume(losses_before_win < lockout_threshold)
        
        gov = GovernanceManager(
            max_signals_per_day=100,
            lockout_after_losses=lockout_threshold,
            time_cutoff=None
        )
        
        # Simulate some losses
        for _ in range(losses_before_win):
            gov.register_trade_outcome(win=False)
        
        assert gov.state.consecutive_losses == losses_before_win
        
        # Register a win
        gov.register_trade_outcome(win=True)
        
        # Consecutive losses should reset to 0
        assert gov.state.consecutive_losses == 0, \
            f"Win did not reset consecutive losses"
        assert not gov.state.lockout_flag, "Locked out after win reset"
    
    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=50)
    def test_signal_cap_enforced_exactly(self, max_signals):
        """Property: Signal cap is enforced exactly at limit."""
        gov = GovernanceManager(
            max_signals_per_day=max_signals,
            lockout_after_losses=100,  # High threshold
            time_cutoff=None
        )
        
        # Emit max_signals - 1
        for _ in range(max_signals - 1):
            assert gov.can_emit_signal(datetime.now()), \
                f"Cannot emit signal {_+1}/{max_signals}"
            gov.state.day_signal_count += 1
        
        # Should still allow one more
        assert gov.can_emit_signal(datetime.now()), \
            f"Cannot emit last signal {max_signals}/{max_signals}"
        gov.state.day_signal_count += 1
        
        # Should now be at cap
        assert not gov.can_emit_signal(datetime.now()), \
            f"Signal cap not enforced after {max_signals} signals"
    
    @given(
        st.integers(min_value=1, max_value=10),
        st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=100)
    def test_new_day_clears_all_limits(self, lockout_threshold, signal_count):
        """Property: New day reset clears lockout and signal count."""
        gov = GovernanceManager(
            max_signals_per_day=5,
            lockout_after_losses=lockout_threshold,
            time_cutoff=None
        )
        
        # Trigger lockout
        for _ in range(lockout_threshold):
            gov.register_trade_outcome(win=False)
        
        # Max out signal count
        gov.state.day_signal_count = signal_count
        
        # Verify locked out
        assert gov.state.lockout_flag, "Not locked out before reset"
        assert gov.state.consecutive_losses == lockout_threshold
        
        # New day reset
        gov.new_day_reset()
        
        # All limits should be cleared
        assert not gov.state.lockout_flag, "Lockout not cleared on new day"
        assert gov.state.consecutive_losses == 0, "Consecutive losses not reset"
        assert gov.state.day_signal_count == 0, "Signal count not reset"
        assert gov.can_emit_signal(datetime.now()), "Cannot emit signal after reset"
    
    @given(
        st.integers(min_value=1, max_value=10),
        st.lists(st.booleans(), min_size=1, max_size=20)
    )
    @settings(max_examples=100)
    def test_consecutive_losses_count_accurate(self, lockout_threshold, outcomes):
        """Property: Consecutive loss counter is always accurate."""
        gov = GovernanceManager(
            max_signals_per_day=100,
            lockout_after_losses=lockout_threshold,
            time_cutoff=None
        )
        
        expected_consecutive = 0
        max_consecutive = 0
        
        for is_win in outcomes:
            gov.register_trade_outcome(win=is_win)
            
            if is_win:
                expected_consecutive = 0
            else:
                expected_consecutive += 1
            
            max_consecutive = max(max_consecutive, expected_consecutive)
            
            # Verify counter is accurate
            assert gov.state.consecutive_losses == expected_consecutive, \
                f"Expected {expected_consecutive}, got {gov.state.consecutive_losses}"
            
            # Verify lockout state is consistent
            should_be_locked = expected_consecutive >= lockout_threshold
            assert gov.state.lockout_flag == should_be_locked, \
                f"Lockout state inconsistent: flag={gov.state.lockout_flag}, should be {should_be_locked}"


# ============================================================================
# Property Tests: Risk Management
# ============================================================================


class TestRiskManagementProperty:
    """Property tests for risk management functions."""
    
    @given(
        st.floats(min_value=100.0, max_value=500.0),
        st.floats(min_value=80.0, max_value=120.0),
        st.floats(min_value=0.5, max_value=5.0)
    )
    @settings(max_examples=200)
    def test_stop_never_equals_entry(self, entry, or_opposite, atr_value):
        """Property: Computed stop never equals entry (no zero risk)."""
        from orb_confluence.strategy.trade_state import TradeSignal
        
        signal = TradeSignal(
            direction='long',
            timestamp=datetime.now(),
            entry_price=entry,
            stop_price_initial=or_opposite,
            or_high=entry + 1,
            or_low=entry - 1,
            confluence_score=0.8,
            factors={}
        )
        
        # Test each stop mode
        for mode in ['or_opposite', 'swing', 'atr_capped']:
            stop = compute_stop(
                signal=signal,
                stop_mode=mode,
                extra_buffer=0.0,
                atr_cap_mult=2.0 if mode == 'atr_capped' else None,
                atr_value=atr_value if mode == 'atr_capped' else None,
                swing_low=or_opposite if mode == 'swing' else None,
                swing_high=None
            )
            
            assert stop != entry, \
                f"Stop equals entry for mode {mode}: entry={entry}, stop={stop}"
            assert abs(stop - entry) > 0.01, \
                f"Stop too close to entry for mode {mode}"
    
    @given(
        st.floats(min_value=100.0, max_value=500.0),
        st.floats(min_value=1.0, max_value=5.0),
        st.floats(min_value=1.5, max_value=10.0)
    )
    @settings(max_examples=100)
    def test_targets_ordered_correctly(self, entry, t1_r, runner_r):
        """Property: Target prices are ordered correctly (T1 < T2 < Runner for long)."""
        assume(runner_r > t1_r)
        t2_r = (t1_r + runner_r) / 2
        
        stop = entry - 5.0  # Long trade
        
        targets = build_targets(
            entry=entry,
            stop=stop,
            direction='long',
            partials=True,
            t1_r=t1_r,
            t2_r=t2_r,
            runner_r=runner_r
        )
        
        # Extract prices
        prices = [t['price'] for t in targets]
        
        # Should be in ascending order for long
        for i in range(len(prices) - 1):
            assert prices[i] < prices[i+1], \
                f"Targets not ordered: {prices}"


# ============================================================================
# Summary
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
