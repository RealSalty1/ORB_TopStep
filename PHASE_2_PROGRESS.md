# Phase 2 Progress: Playbook Architecture

**Date:** October 8, 2025  
**Status:** 🔄 In Progress  
**Completed:** Playbook Base + IB Fade  

---

## What We've Built So Far

### 1. Playbook Base Architecture ✅
**File:** `orb_confluence/strategy/playbook_base.py` (580 lines)

**Core Classes:**

#### **Direction Enum**
- `LONG` / `SHORT` trade directions

#### **SignalStrength Enum**
- `WEAK` (0-0.4)
- `MODERATE` (0.4-0.7)
- `STRONG` (0.7-1.0)

#### **ProfitTarget Dataclass**
```python
@dataclass
class ProfitTarget:
    price: float           # Target price
    size_pct: float        # % of position (0-1)
    label: str             # Description
    r_multiple: float      # Expected R at target
```

#### **Signal Dataclass**
Complete trading signal with validation:
- Entry price & direction
- Initial stop loss
- Multiple profit targets
- Signal strength & confidence
- Regime alignment score
- Metadata dictionary
- Timestamp

**Validation:**
- Strength/alignment/confidence must be 0-1
- Stop must be on correct side of entry
- Automatic R-multiple calculation

#### **PlaybookStats**
Tracks performance metrics:
- Win rate
- Expectancy
- Average win/loss
- Total R
- Sharpe ratio
- Bars in trade

#### **Playbook Abstract Base Class**
All playbooks must implement:
- `check_entry()` - Signal generation
- `update_stops()` - Three-phase stop management
- `check_salvage()` - Early exit conditions
- `name`, `description`, `preferred_regimes`, `playbook_type` properties

**Built-in Methods:**
- `get_regime_alignment()` - Calculate fit with current regime
- `calculate_position_size()` - Risk-based sizing
- `update_stats()` - Track performance
- `get_summary()` - Performance report

#### **PlaybookRegistry**
Centralized playbook management:
- Register/unregister playbooks
- Get playbooks by regime
- Get playbooks by type
- Enable/disable playbooks
- Performance summaries

---

### 2. Initial Balance Fade Playbook ✅
**File:** `orb_confluence/strategy/playbooks/ib_fade.py` (650 lines)

**Strategy Logic:**
Fades weak extensions beyond the Initial Balance (first hour range)

**Key Features:**

#### **Auction Efficiency Ratio (AER)**
```
AER = (Extension Range / Sum of TRs) × (Extension Vol / Expected Vol)
```
- Low AER (<0.65) = weak conviction = fade opportunity
- Measures both price and volume efficiency

#### **Initial Balance Calculation**
- Configurable period (default: 60 minutes)
- Tracks IB high, low, midpoint, range
- Caches for efficiency

#### **Extension Detection**
- Minimum extension threshold (default: 1.5x IB range)
- Minimum extension in ticks (default: 8)
- Detects both upside and downside extensions

#### **Acceptance Velocity**
- Monitors price returning to IB
- Requires minimum acceptance bars (default: 3)
- Checks momentum direction

#### **Entry Conditions**
1. ✅ IB established (>= 60 minutes)
2. ✅ Extension beyond IB (1.5x range or 8+ ticks)
3. ✅ Low AER (<0.65) - weak conviction
4. ✅ Acceptance showing (price returning)
5. ✅ Regime alignment (RANGE/VOLATILE preferred)

#### **Profit Targets**
- **T1 (50%)**: IB midpoint
- **T2 (30%)**: Opposite IB extreme
- **T3 (20%)**: Runner (1.5x to extreme)

#### **Three-Phase Stops**
- **Phase 1 (0-0.5R MFE)**: Keep initial stop
- **Phase 2 (0.5-1.25R MFE)**: Move to breakeven +0.1R
- **Phase 3 (>1.25R MFE)**: Trail with recent swing

#### **Salvage Conditions**
1. Retraced >70% from MFE after reaching 0.5R+
2. Stalled >45 bars with <0.3R movement
3. Velocity decay (losing momentum)

#### **Signal Strength Calculation**
Weighted factors:
- 50% AER score (lower = stronger)
- 30% Extension size (larger = stronger)
- 20% Rotation entropy (higher = stronger)

---

## Code Statistics

```
Phase 2 So Far:
- playbook_base.py:     580 lines
- ib_fade.py:           650 lines
- __init__.py:           13 lines
Total:                 1,243 lines
```

**With Phase 1:**
- Total production code: ~2,900 lines
- Total test code: ~550 lines
- **Grand Total: ~3,450 lines**

---

## Design Decisions

### 1. Abstract Base Class Pattern
✅ **Pros:**
- Enforces consistent interface
- Type safety with abstract methods
- Easy to add new playbooks
- Clear documentation of requirements

### 2. Dataclass for Signals
✅ **Pros:**
- Immutable, validated data
- Auto-generated __init__, __repr__
- Type hints built-in
- Easy serialization

### 3. Embedded Statistics
✅ **Pros:**
- Each playbook tracks own performance
- Used for signal arbitration
- Real-time expectancy updates
- No external database needed

### 4. Configuration Dictionaries
✅ **Pros:**
- Easy to tune parameters
- Can save/load configurations
- Version control friendly
- Runtime adjustable

---

## Integration Points

### With Phase 1 (Foundation)
- ✅ Uses `AdvancedFeatures` for signal strength
- ✅ Uses regime from `RegimeClassifier`
- ✅ Compatible with existing data structures

### With Future Phases
- **Phase 3 (Risk Management)**: Three-phase stops ready
- **Phase 4 (Orchestration)**: Signal arbitration hooks ready
- **Phase 5 (Backtesting)**: Compatible with existing engine

---

## Testing Strategy

### Unit Tests Needed
1. ✅ Playbook base validation (Signal, ProfitTarget)
2. ⏳ IB calculation edge cases
3. ⏳ AER calculation accuracy
4. ⏳ Extension detection logic
5. ⏳ Acceptance velocity detection
6. ⏳ Stop management phases
7. ⏳ Salvage conditions
8. ⏳ Signal strength calculation

### Integration Tests Needed
1. ⏳ Full playbook with real data
2. ⏳ Multiple playbooks in registry
3. ⏳ Regime-based playbook selection
4. ⏳ Performance tracking over time

---

## Next Steps

### Immediate
1. Create unit tests for IB Fade playbook
2. Test on historical data
3. Validate AER calculations

### This Week
1. ✅ IB Fade complete
2. ⏳ VWAP Magnet playbook
3. ⏳ Momentum Continuation playbook
4. ⏳ Opening Drive Reversal playbook

---

## Performance Expectations

### IB Fade Target Metrics
Based on Dr. Hoffman's analysis:
- **Win Rate:** 50-55%
- **Avg Win:** 1.4-1.8R
- **Avg Loss:** 0.85-0.95R
- **Expectancy:** 0.18-0.25R
- **Best Regimes:** RANGE, VOLATILE
- **Trades/Month:** 10-20

### Risk Parameters
- Initial stop: Beyond extension extreme + 20% buffer
- Max risk per trade: 1% of account
- Position sizing: Risk-based (accounts for point value)

---

## Known Limitations

### Current
1. No sub-minute data yet (using 1m bars)
2. AER calculation needs more validation
3. Acceptance detection could be refined
4. No session-specific adjustments yet

### Future Enhancements
1. Add seasonality matrix (day-of-week, month-end)
2. Distribution tail analysis (>92nd percentile)
3. Multi-timeframe confirmation
4. Volume profile integration

---

## Example Usage

```python
from orb_confluence.strategy.playbooks import IBFadePlaybook
from orb_confluence.strategy.playbook_base import PlaybookRegistry

# Create playbook
ib_fade = IBFadePlaybook(
    ib_minutes=60,
    extension_threshold=1.5,
    max_aer=0.65,
)

# Register
registry = PlaybookRegistry()
registry.register(ib_fade)

# Check for signals
signal = ib_fade.check_entry(
    bars=historical_bars,
    current_bar=current_bar,
    regime="RANGE",
    features=current_features,
    open_positions=[],
)

if signal:
    print(f"Signal: {signal.direction.value} @ {signal.entry_price}")
    print(f"Stop: {signal.initial_stop}")
    print(f"Strength: {signal.strength:.2f}")
    print(f"Targets: {[t.label for t in signal.profit_targets]}")
```

---

## Documentation

### Docstrings
- ✅ All classes documented
- ✅ All methods documented
- ✅ Type hints throughout
- ✅ Examples in docstrings

### Code Comments
- ✅ Key algorithms explained
- ✅ Formula citations
- ✅ Edge cases noted
- ✅ References to Dr. Hoffman's review

---

## Validation Checklist

### IB Fade Playbook
- ✅ Implements all abstract methods
- ✅ Proper validation in check_entry
- ✅ Three-phase stops implemented
- ✅ Salvage conditions defined
- ✅ Signal strength calculation
- ✅ AER formula matches specification
- ✅ Regime alignment checked
- ⏳ Tested on historical data
- ⏳ Performance metrics validated

---

## Estimated Completion

**Phase 2 Total:** ~4-5 sessions
**Completed:** 2/5 (40%)

**Remaining:**
- VWAP Magnet (1 session)
- Momentum Continuation (1 session)
- Opening Drive Reversal (1 session)
- Testing & validation (1 session)

---

## Key Insights

### What Worked Well
1. **Abstract base class** provides clear structure
2. **Dataclasses** make signals clean and validated
3. **Embedded stats** simplify performance tracking
4. **Config dicts** make tuning easy

### Challenges
1. AER calculation more complex than expected
2. Acceptance detection needs refinement
3. Need more edge case handling

### Lessons Learned
1. Start with simplest playbook first (good choice with IB Fade)
2. Build abstractions incrementally
3. Document as you go
4. Test edge cases early

---

**Status:** Phase 2 is 40% complete. Foundation is solid. Ready to add more playbooks.

---

*Updated: October 8, 2025, 6:45 PM*

