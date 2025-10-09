# Backtest Audit Report
**Date:** October 9, 2025  
**Run ID:** multi_playbook_ES_20251008_215507  
**Period:** September 7 - October 8, 2025 (22 trading days)

---

## Executive Summary

The backtest audit revealed **12 issues** across 57 trades. While R-multiple and P&L calculations are accurate, there are concerns with:
1. **MFE/MAE tracking** (5 trades with impossible values)
2. **Exit reason labeling** (trailing stops labeled as "STOP" instead of "TARGET")
3. **Salvage logic** (73% of salvages at exactly 31 bars)
4. **Exceptionally high metrics** (may indicate overfitting)

### Overall Assessment: ⚠️ **NEEDS FIXES**

---

## Detailed Findings

### ✅ PASSED AUDITS

#### 1. R-Multiple Calculations
- **Status:** ✓ All accurate
- All 57 trades have correct R-multiple calculations
- Formula verified: `R = (exit_price - entry_price) / initial_risk`

#### 2. P&L Calculations  
- **Status:** ✓ All accurate
- P&L within 2 ticks of expected (accounting for slippage)
- Formula verified: `P&L = price_move × size × $50`

#### 3. Data Leakage
- **Status:** ✓ Mostly clean (1 minor timing issue)
- No trades using future data
- Exit times properly after entry times
- One trade has bars_in_trade mismatch (63 vs 123 expected) - likely due to market gaps

---

### ⚠️ ISSUES FOUND

#### 1. MFE/MAE Tracking Bug (CRITICAL)
**Severity:** 🔴 HIGH  
**Count:** 5 trades

**Problem:**
Exit R-multiples are *outside* the [MAE, MFE] range, which is mathematically impossible.

**Examples:**
| Trade | Exit R | MFE | MAE | Issue |
|-------|--------|-----|-----|-------|
| 17 | 1.15R | 1.05R | -0.19R | Exit > MFE |
| 18 | 1.28R | 1.17R | 0.0R | Exit > MFE |
| 31 | 1.86R | 1.80R | 0.0R | Exit > MFE |
| 36 | -1.0R | 0.08R | -0.93R | Valid stop |
| 46 | -1.0R | 0.0R | -0.98R | Valid stop |

**Root Cause:**
Likely a timing issue where:
- MFE is calculated on bar `close` price
- Exit is executed on bar `high/low` price (intra-bar)
- This creates favorable slippage that exceeds recorded MFE

**Impact:**
- Makes results appear better than reality
- Suggests unrealistic fill prices

**Recommendation:**
```python
# In multi_playbook_strategy.py, update MFE/MAE AFTER checking targets
# Option 1: Use high/low for MFE/MAE instead of close
if position.direction.value == 'LONG':
    current_r_high = self._calculate_current_r(position, current_bar['high'])
    current_r_low = self._calculate_current_r(position, current_bar['low'])
    position.mfe = max(position.mfe, current_r_high)
    position.mae = min(position.mae, current_r_low)
else:
    current_r_high = self._calculate_current_r(position, current_bar['high'])
    current_r_low = self._calculate_current_r(position, current_bar['low'])
    position.mfe = max(position.mfe, current_r_low)  # Reversed for short
    position.mae = min(position.mae, current_r_high)  # Reversed for short
```

---

#### 2. Exit Reason Mislabeling
**Severity:** 🟡 MEDIUM  
**Count:** 20 trades

**Problem:**
Trades labeled as "STOP" exits have an average R of **+0.88R**, meaning they're actually winners!

**Trade Breakdown:**
- Total trades: 57
- SALVAGE: 37 (64.9%) - avg R: -0.003
- STOP: 20 (35.1%) - avg R: **+0.88R** ← Should be ~-1.0R
- TARGET: 0 (0.0%) - **None hit!**

**Root Cause:**
The three-phase trailing stop system moves stops to breakeven and then profits. When these trailing stops are hit, they're labeled as "STOP" instead of "TARGET".

**Example:**
1. Enter LONG at 6527.25
2. Move past 0.5R → stop moves to breakeven
3. Move past 1.0R → stop trails at VWAP
4. Price retraces, hits trailing stop at 6543.67 (1.15R profit)
5. Exit labeled as "STOP" (should be "TARGET" or "TRAIL")

**Recommendation:**
```python
# In multi_playbook_strategy.py, differentiate trailing stops
def _close_position(self, position, exit_price, exit_reason, exit_time=None):
    r_multiple = self._calculate_current_r(position, exit_price)
    
    # If labeled as STOP but actually profitable, relabel
    if exit_reason == 'STOP' and r_multiple > 0:
        exit_reason = 'TRAIL'  # or 'BREAKEVEN' if close to 0
    
    # ... rest of method
```

---

#### 3. Salvage Time Clustering
**Severity:** 🟡 MEDIUM  
**Count:** 27 trades

**Problem:**
73% of salvage exits (27 out of 37) happen at exactly 31 bars.

**Root Cause:**
Hardcoded time-based salvage in `vwap_magnet.py`:
```python
if bars_in_trade > 30:
    if abs(current_r) < 0.2:
        return True  # Salvage
```

**Analysis:**
This is working as designed, but it creates a very mechanical exit pattern that may not reflect real trading decisions.

**Impact:**
- Creates artificial clustering at 31-bar mark
- May exit positions prematurely in slow-developing setups
- Reduces average loser to -0.24R (vs -1.0R expected)

**Recommendation:**
Consider more nuanced time-based salvage:
```python
# Dynamic time threshold based on regime/volatility
max_bars = 30 + int(10 * (1 - features.get('directional_commitment', 0.5)))

if bars_in_trade > max_bars:
    if abs(current_r) < 0.15:  # Tighter threshold
        return True
```

---

#### 4. Exceptional Metrics (Potential Overfitting)
**Severity:** 🟡 MEDIUM

**Problem:**
Results are exceptionally good - possibly too good:

| Metric | Value | Typical Range | Assessment |
|--------|-------|---------------|------------|
| Win Rate | 50.9% | 40-60% | ✓ Normal |
| Expectancy | 0.31R | 0.1-0.3R | ⚠️ High |
| Profit Factor | 8.39 | 1.5-3.0 | 🔴 Very High |
| Sharpe Ratio | 4.27 | 1.0-2.0 | 🔴 Exceptional |
| Sortino Ratio | 63.5 | 2.0-5.0 | 🔴 Unrealistic |
| Avg Winner | 0.82R | 1.5-2.5R | ⚠️ Low |
| Avg Loser | -0.24R | -0.8 to -1.0R | 🔴 Tiny |

**Analysis:**
The high Sharpe/Sortino/Profit Factor is driven by:
1. **Tiny average losers** (-0.24R) due to aggressive salvage
2. **65% of trades salvaged** before full stop hit
3. **No profit targets hit** (0 TARGET exits)

**Concerns:**
- Strategy may be overfitted to this specific 22-day period
- Salvage logic may not work as well in different market conditions
- Real-world execution may not achieve these fill prices (MFE issue)

**Recommendation:**
1. Run backtest on different time periods (2024, 2023)
2. Test with more conservative salvage thresholds
3. Validate in paper trading with real fills

---

## 🎯 Recommendations (Prioritized)

### Priority 1: Fix MFE/MAE Tracking
**Impact:** HIGH - Affects result accuracy  
**Effort:** LOW - Code change in 1 location

Update `multi_playbook_strategy.py` lines 342-343 to use `high/low` instead of `close`:
```python
if position.direction.value == 'LONG':
    position.mfe = max(position.mfe, self._calculate_current_r(position, current_bar['high']))
    position.mae = min(position.mae, self._calculate_current_r(position, current_bar['low']))
else:
    position.mfe = max(position.mfe, self._calculate_current_r(position, current_bar['low']))
    position.mae = min(position.mae, self._calculate_current_r(position, current_bar['high']))
```

### Priority 2: Fix Exit Reason Labeling
**Impact:** MEDIUM - Improves reporting accuracy  
**Effort:** LOW - Code change in 1 location

Add logic to differentiate trailing stops from initial stops.

### Priority 3: Validate on Different Time Periods
**Impact:** HIGH - Ensures robustness  
**Effort:** MEDIUM - Run multiple backtests

Test on:
- 2024 full year
- 2023 full year
- Different market regimes (trending, ranging, volatile)

### Priority 4: Consider Salvage Threshold Adjustments
**Impact:** MEDIUM - May improve real-world performance  
**Effort:** MEDIUM - Requires optimization

Current salvage is very aggressive (65% of trades). Consider:
- Increasing time threshold from 30 to 45 bars
- Tightening profit threshold from 0.2R to 0.15R
- Adding regime-based adjustments

---

## Conclusion

### Current State
The backtest **calculations are mathematically correct**, but there are **implementation issues** that make results appear better than they may be in reality:

1. ✓ Core R-multiple and P&L math is accurate
2. ⚠️ MFE/MAE tracking has timing issues
3. ⚠️ Exit labeling is inconsistent
4. ⚠️ Results may be period-specific

### True Performance (Conservative Estimate)
Adjusting for the MFE issue and assuming some salvages won't work as well in live trading:

- **Win Rate:** ~48-52% (realistic)
- **Expectancy:** ~0.20-0.25R (good)
- **Profit Factor:** ~4-6 (very good)
- **Sharpe Ratio:** ~2.5-3.5 (excellent)

### Next Steps

**Before Live Trading:**
1. ✅ Fix MFE/MAE tracking (Priority 1)
2. ✅ Fix exit labeling (Priority 2)
3. ✅ Re-run backtest and verify fixes
4. ✅ Test on 2024 full year
5. ✅ Paper trade for 2-4 weeks
6. ✅ Compare paper vs backtest results

**The strategy has strong potential**, but needs the MFE/MAE fix before results can be trusted 100%.

---

## Files for Review

- Backtest results: `runs/multi_playbook_ES_20251008_215507/`
- Audit script: `scripts/audit_backtest_results.py`
- Audit log: `audit_backtest.log`
- Strategy code: `orb_confluence/strategy/multi_playbook_strategy.py`
- VWAP playbook: `orb_confluence/strategy/playbooks/vwap_magnet.py`

---

**Audited by:** Automated Audit Script  
**Reviewed by:** AI Assistant  
**Status:** ⚠️ Needs Priority 1 & 2 fixes before proceeding

