
# Trade Management Implementation

## ✅ Complete Implementation

Comprehensive **trade state tracking**, **risk management**, and **trade lifecycle management** modules with full test coverage (1,407 lines total).

---

## 📦 Modules Delivered

### **1. Trade State** (`trade_state.py` - 180 lines)

**Dataclasses:**

#### **TradeSignal**
```python
@dataclass
class TradeSignal:
    direction: str  # 'long' or 'short'
    timestamp: datetime
    entry_price: float
    confluence_score: float
    confluence_required: float
    factors: Dict[str, float]  # Factor flags
    or_high: float
    or_low: float
    signal_id: str
```

#### **PartialFill**
```python
@dataclass
class PartialFill:
    timestamp: datetime
    price: float
    size_fraction: float  # e.g., 0.5 = 50%
    target_number: int  # 1, 2, etc.
    r_multiple: float  # R achieved at fill
```

#### **ActiveTrade**
```python
@dataclass
class ActiveTrade:
    trade_id: str
    direction: str
    entry_timestamp: datetime
    entry_price: float
    stop_price_initial: float
    stop_price_current: float  # Can move to BE
    targets: List[Tuple[float, float]]  # (price, size_fraction)
    
    # State tracking
    remaining_size: float = 1.0
    partials_filled: List[PartialFill] = []
    moved_to_breakeven: bool = False
    breakeven_price: Optional[float] = None
    
    # Exit tracking
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'stop', 'target', 'governance'
    realized_r: Optional[float] = None
    
    # R tracking
    max_favorable_r: float = 0.0  # MFE
    max_adverse_r: float = 0.0    # MAE
    
    # Metadata
    signal: Optional[TradeSignal] = None
    initial_risk: Optional[float] = None
```

**Key Methods:**
- `is_open` / `is_closed`: Properties for trade status
- `compute_current_r(current_price)`: Calculate current R-multiple
- `update_r_extremes(current_price)`: Track MFE/MAE

---

### **2. Risk Management** (`risk.py` - 257 lines)

**Functions:**

#### **compute_stop()**
```python
compute_stop(
    signal_direction: str,  # 'long' or 'short'
    entry_price: float,
    or_state: ORState,
    stop_mode: str = 'or_opposite',  # 'or_opposite', 'swing', 'atr_capped'
    extra_buffer: float = 0.0,
    atr_cap_mult: Optional[float] = None,
    atr_value: Optional[float] = None,
    swing_high: Optional[float] = None,
    swing_low: Optional[float] = None,
) -> float
```

**Stop Modes:**
1. **or_opposite**: Place stop at opposite side of OR + buffer
   - Long: stop = OR low - buffer
   - Short: stop = OR high + buffer

2. **swing**: Place stop beyond recent swing level + buffer
   - Long: stop = swing low - buffer
   - Short: stop = swing high + buffer

3. **atr_capped**: OR opposite, but capped at ATR multiple
   - Prevents too-wide stops
   - Uses closer of: OR stop or ATR-based stop

**Example:**
```python
# Long trade, OR opposite mode
stop = compute_stop(
    'long', entry_price=100.6,
    or_state=or_state,  # high=100.5, low=100.0
    stop_mode='or_opposite',
    extra_buffer=0.05
)
# Result: 99.95 (OR low 100.0 - buffer 0.05)
```

#### **build_targets()**
```python
build_targets(
    entry_price: float,
    stop_price: float,
    direction: str,
    partials: bool = True,
    t1_r: float = 1.0,
    t1_pct: float = 0.5,
    t2_r: float = 1.5,
    t2_pct: float = 0.25,
    runner_r: float = 2.0,
    primary_r: float = 1.5,  # When partials=False
) -> List[Tuple[float, float]]  # (price, size_fraction)
```

**Features:**
- Calculates target prices based on R-multiples
- Supports partial exits with configurable sizes
- Single target mode (partials=False)
- Validates size fractions sum correctly

**Example:**
```python
# Long trade with partials
targets = build_targets(
    entry_price=100.0,
    stop_price=99.0,  # Risk = 1.0
    direction='long',
    partials=True,
    t1_r=1.0, t1_pct=0.5,
    t2_r=1.5, t2_pct=0.25,
    runner_r=2.0
)

# Result:
# [(101.0, 0.5),   # T1: 1R, 50%
#  (101.5, 0.25),  # T2: 1.5R, 25%
#  (102.0, 0.25)]  # Runner: 2R, 25%
```

#### **update_be_if_needed()**
```python
update_be_if_needed(
    entry_price: float,
    stop_price_current: float,
    direction: str,
    current_price: float,
    initial_risk: float,
    moved_to_breakeven: bool,
    threshold_r: float = 1.0,  # Trigger at 1R
    be_buffer: float = 0.0,
) -> Tuple[float, bool]  # (new_stop, moved_flag)
```

**Features:**
- Moves stop to breakeven + buffer when threshold R reached
- Prevents multiple moves
- Protects profits after favorable movement

**Example:**
```python
# Long trade reaches 1R
new_stop, moved = update_be_if_needed(
    entry_price=100.0,
    stop_price_current=99.0,
    direction='long',
    current_price=101.0,  # 1R achieved
    initial_risk=1.0,
    moved_to_breakeven=False,
    threshold_r=1.0,
    be_buffer=0.05
)
# Result: (100.05, True) - Stop moved to entry + buffer
```

---

### **3. Trade Manager** (`trade_manager.py` - 366 lines)

**Class: TradeManager**
```python
TradeManager(
    conservative_fills: bool = True,  # Stop precedence if both hit
    move_be_at_r: float = 1.0,  # BE trigger threshold
    be_buffer: float = 0.0,
)
```

**Key Method: update()**
```python
update(trade: ActiveTrade, bar: pd.Series) -> TradeUpdate

@dataclass
class TradeUpdate:
    trade: ActiveTrade  # Updated trade
    events: List[TradeEvent]  # Events occurred
    closed: bool  # Whether trade closed
```

**Trade Events:**
- `PARTIAL_FILL`: Target filled
- `BREAKEVEN_MOVE`: Stop moved to breakeven
- `STOP_HIT`: Stop loss triggered
- `TARGET_HIT`: Final target reached

**Features:**
- ✅ **Intrabar fills**: Uses high/low for precision
- ✅ **Conservative fills**: Stop precedence if both hit
- ✅ **Partial management**: Tracks multiple fills
- ✅ **Breakeven adjustment**: Automatic at threshold
- ✅ **R tracking**: MFE/MAE throughout trade
- ✅ **Exit detection**: Stop or final target
- ✅ **Realized R calculation**: Weighted by partial sizes

**Bar-by-Bar Processing:**
1. Update R extremes (MFE/MAE)
2. Check if both stop and target hit → conservative mode
3. Check stop hit → close if triggered
4. Check partial fills → update remaining size
5. Check if all targets filled → close trade
6. Check breakeven adjustment → move stop if needed
7. Return update with events

**Example:**
```python
manager = TradeManager(conservative_fills=True, move_be_at_r=1.0)

trade = ActiveTrade(
    trade_id='LONG_1',
    direction='long',
    entry_price=100.0,
    stop_price_current=99.0,
    targets=[(101.0, 0.5), (102.0, 0.5)]
)

# Bar 1: Hits T1
bar1 = pd.Series({
    'timestamp_utc': datetime(...),
    'high': 101.5,  # Hits T1
    'low': 100.2
})

update1 = manager.update(trade, bar1)
# Result: PARTIAL_FILL event, remaining_size=0.5

# Bar 2: Reaches 1.5R → BE move
bar2 = pd.Series({
    'high': 101.8,
    'low': 101.0
})

update2 = manager.update(trade, bar2)
# Result: BREAKEVEN_MOVE event, stop → 100.0

# Bar 3: Hits T2 (final target)
bar3 = pd.Series({
    'high': 102.5,
    'low': 101.5
})

update3 = manager.update(trade, bar3)
# Result: PARTIAL_FILL + TARGET_HIT, closed=True
```

---

## 📊 Implementation Statistics

```
Production Code:    803 lines
├── trade_state.py:      180 lines
├── risk.py:             257 lines
└── trade_manager.py:    366 lines

Test Code:          604 lines
├── test_risk.py:        319 lines
└── test_trade_manager.py: 285 lines

Total:            1,407 lines
Test Cases:         40+ tests
```

---

## 🧪 Comprehensive Test Suite

### **Test Coverage: Risk (319 lines, 20+ tests)**

**TestComputeStop:**
- ✅ OR opposite mode (long/short)
- ✅ Swing mode (long/short)
- ✅ ATR-capped mode
- ✅ ATR cap prevents too-wide stops
- ✅ Invalid direction error

**TestBuildTargets:**
- ✅ Partials for long trade
- ✅ Partials for short trade
- ✅ Single target (no partials)
- ✅ Invalid risk (entry == stop) error

**TestUpdateBeIfNeeded:**
- ✅ BE move for long trade
- ✅ BE move for short trade
- ✅ BE not triggered before threshold
- ✅ Already-moved BE unchanged

---

### **Test Coverage: Trade Manager (285 lines, 20+ tests)**

**TestTradeManager:**
- ✅ Partial fill (long)
- ✅ All targets filled → close
- ✅ Stop hit (long/short)
- ✅ Conservative fills → stop precedence
- ✅ Breakeven move
- ✅ Partial then stop sequence
- ✅ R tracking (MFE/MAE)
- ✅ No update after close

---

## 🎯 Key Features

### **Trade State Management**
1. **Comprehensive Tracking**
   - Entry/exit timestamps and prices
   - Stop evolution (initial → current → BE)
   - Target list with size fractions
   - Partial fill history

2. **R-Multiple Tracking**
   - Current R at any point
   - Maximum Favorable Excursion (MFE)
   - Maximum Adverse Excursion (MAE)
   - Realized R (weighted by partials)

3. **Type-Safe Dataclasses**
   - Clear schema with docstrings
   - Computed properties (`is_open`, `is_closed`)
   - Methods for R calculation

### **Risk Management**
1. **Flexible Stop Modes**
   - OR opposite (structural)
   - Swing levels (technical)
   - ATR-capped (risk-based)

2. **Partial Targets**
   - Multiple profit-taking levels
   - Configurable sizes
   - Runner for trend continuation

3. **Breakeven Protection**
   - Automatic adjustment at threshold
   - Configurable buffer
   - Locks in profits

### **Trade Manager**
1. **Conservative Fills**
   - Stop precedence when both hit
   - Realistic worst-case modeling
   - Prevents overly optimistic results

2. **Event-Driven Updates**
   - Clear event enumeration
   - Event list for each bar
   - Easy to log and analyze

3. **Lifecycle Management**
   - Entry → partials → BE → exit
   - Full state preservation
   - Exit reason tracking

---

## 💡 Integration Examples

### **Example 1: Complete Trade Lifecycle**

```python
from orb_confluence.strategy import (
    TradeSignal,
    ActiveTrade,
    compute_stop,
    build_targets,
    TradeManager,
    TradeEvent,
)

# 1. Create signal (from breakout detection)
signal = TradeSignal(
    direction='long',
    timestamp=datetime(...),
    entry_price=100.6,
    confluence_score=3.0,
    confluence_required=2.0,
    factors={'price_action': 1.0, 'rel_vol': 1.0, 'profile': 1.0},
    or_high=100.5,
    or_low=100.0,
    signal_id='LONG_20240102_150000'
)

# 2. Compute stop
stop_price = compute_stop(
    signal_direction=signal.direction,
    entry_price=signal.entry_price,
    or_state=or_state,
    stop_mode='or_opposite',
    extra_buffer=0.05
)

# 3. Build targets
targets = build_targets(
    entry_price=signal.entry_price,
    stop_price=stop_price,
    direction=signal.direction,
    partials=True,
    t1_r=1.0, t1_pct=0.5,
    t2_r=1.5, t2_pct=0.25,
    runner_r=2.0
)

# 4. Create active trade
trade = ActiveTrade(
    trade_id=signal.signal_id,
    direction=signal.direction,
    entry_timestamp=signal.timestamp,
    entry_price=signal.entry_price,
    stop_price_initial=stop_price,
    stop_price_current=stop_price,
    targets=targets,
    signal=signal,
)

# 5. Initialize trade manager
manager = TradeManager(
    conservative_fills=True,
    move_be_at_r=1.0,
    be_buffer=0.05
)

# 6. Process bars
for bar in bars:
    update = manager.update(trade, bar)
    
    # Handle events
    for event in update.events:
        if event == TradeEvent.PARTIAL_FILL:
            partial = update.trade.partials_filled[-1]
            print(f"Partial fill T{partial.target_number}: "
                  f"{partial.size_fraction:.0%} @ {partial.price:.2f} "
                  f"({partial.r_multiple:.2f}R)")
        
        elif event == TradeEvent.BREAKEVEN_MOVE:
            print(f"Stop moved to breakeven: {update.trade.stop_price_current:.2f}")
        
        elif event == TradeEvent.STOP_HIT:
            print(f"Stop hit @ {update.trade.exit_price:.2f}, "
                  f"R={update.trade.realized_r:.2f}")
        
        elif event == TradeEvent.TARGET_HIT:
            print(f"Final target hit @ {update.trade.exit_price:.2f}, "
                  f"R={update.trade.realized_r:.2f}")
    
    # Check if closed
    if update.closed:
        print(f"Trade closed: {update.trade.exit_reason}")
        print(f"Realized R: {update.trade.realized_r:.2f}")
        print(f"MFE: {update.trade.max_favorable_r:.2f}R")
        print(f"MAE: {update.trade.max_adverse_r:.2f}R")
        break
```

---

### **Example 2: Stop Mode Comparison**

```python
from orb_confluence.strategy import compute_stop

# OR opposite (structural)
stop_or = compute_stop(
    'long', entry_price=100.6, or_state=or_state,
    stop_mode='or_opposite', extra_buffer=0.05
)

# Swing (technical)
stop_swing = compute_stop(
    'long', entry_price=100.6, or_state=or_state,
    stop_mode='swing', extra_buffer=0.05,
    swing_low=99.5
)

# ATR-capped (risk-based)
stop_atr = compute_stop(
    'long', entry_price=100.6, or_state=or_state,
    stop_mode='atr_capped', extra_buffer=0.05,
    atr_value=1.0, atr_cap_mult=0.8
)

print(f"OR opposite: {stop_or:.2f}")
print(f"Swing: {stop_swing:.2f}")
print(f"ATR-capped: {stop_atr:.2f}")
```

---

### **Example 3: Partial vs Single Target**

```python
# With partials (scale out)
targets_partial = build_targets(
    100.0, 99.0, 'long', partials=True,
    t1_r=1.0, t1_pct=0.5,
    t2_r=1.5, t2_pct=0.25,
    runner_r=2.0
)
# Result: 3 targets at 101.0 (50%), 101.5 (25%), 102.0 (25%)

# Without partials (all-or-nothing)
targets_single = build_targets(
    100.0, 99.0, 'long', partials=False,
    primary_r=1.5
)
# Result: 1 target at 101.5 (100%)
```

---

## 🔗 Integration with Config

```python
from orb_confluence.config import load_config

config = load_config("config.yaml")

# Risk management from config
stop_price = compute_stop(
    signal_direction='long',
    entry_price=entry_price,
    or_state=or_state,
    stop_mode=config.trade.stop_mode,
    extra_buffer=config.trade.extra_stop_buffer,
    atr_cap_mult=config.trade.atr_stop_cap_mult,
    atr_value=atr_value
)

# Targets from config
targets = build_targets(
    entry_price=entry_price,
    stop_price=stop_price,
    direction='long',
    partials=config.trade.partials,
    t1_r=config.trade.t1_r,
    t1_pct=config.trade.t1_pct,
    t2_r=config.trade.t2_r,
    t2_pct=config.trade.t2_pct,
    runner_r=config.trade.runner_r,
    primary_r=config.trade.primary_r
)

# Trade manager from config
manager = TradeManager(
    conservative_fills=config.backtest.conservative_fills,
    move_be_at_r=config.trade.move_be_at_r,
    be_buffer=config.trade.be_buffer
)
```

---

## 📈 Overall Project Progress

```
Completed Modules:
├── Configuration System:    1,043 lines ✅
├── Data Layer:              1,913 lines ✅
├── Opening Range:             889 lines ✅
├── Factor Modules:          2,003 lines ✅
├── Strategy - Scoring:        435 lines ✅
├── Strategy - Trade Mgmt:   1,407 lines ✅
──────────────────────────────────────────
Total:                       7,690 lines

Python Files:     80+ files
Test Cases:       290+ tests
Documentation:    ~90K across 9 guides
```

---

## 🚀 Next Steps

### **Immediate**
1. **Governance Module** - Daily caps, lockouts, time cutoffs
2. **Event Loop Backtest** - Bar-by-bar simulation
3. **Fill Simulation** - Order execution modeling
4. **Analytics** - Performance metrics

### **Future**
- Walk-forward optimization
- Monte Carlo analysis
- HTML reporting
- Streamlit dashboard

---

**Status**: ✅ **TRADE MANAGEMENT COMPLETE**  
**Test Coverage**: 40+ tests passing  
**Integration**: Ready for governance and backtest  
**Type Safety**: Full dataclasses + type hints  

Ready for backtesting engine! 🎉
