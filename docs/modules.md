# Module Organization

## Core Modules

### 1. Configuration (`orb_confluence/config/`)

**Purpose**: YAML-driven configuration with comprehensive validation.

**Key Files:**
- `schema.py` - Pydantic models for all configuration
- `loader.py` - YAML loading with deep merge and hashing

**Features:**
- 15+ Pydantic dataclasses
- 10+ validation rules
- Config hashing (SHA256) for reproducibility
- Layered config merge (defaults + user)

---

### 2. Data Layer (`orb_confluence/data/`)

**Purpose**: Data acquisition, normalization, and quality control.

**Key Files:**
- `sources/yahoo.py` - Yahoo Finance provider
- `sources/binance.py` - Binance crypto provider
- `sources/synthetic.py` - Deterministic synthetic data
- `normalizer.py` - Data normalization pipeline
- `qc.py` - Quality control checks

**Features:**
- 3 data providers (swappable)
- Automatic timezone handling
- Gap detection and OR window validation
- Volume outlier detection

---

### 3. Opening Range (`orb_confluence/features/opening_range.py`)

**Purpose**: Calculate and validate opening range.

**Key Components:**
- `OpeningRangeBuilder` - Streaming OR calculation
- `validate_or()` - ATR-based width validation
- `choose_or_length()` - Adaptive duration selection
- `apply_buffer()` - Buffer application

**Features:**
- Adaptive OR (10/15/30 minutes)
- ATR-based validation (too narrow/wide rejection)
- Buffer support (symmetric/asymmetric)

---

### 4. Factor Modules (`orb_confluence/features/`)

**Purpose**: Calculate confluence factors for signal confirmation.

**Factors:**

1. **Relative Volume** (`relative_volume.py`)
   - Tracks volume vs rolling average
   - Detects volume spikes
   
2. **Price Action** (`price_action.py`)
   - Engulfing patterns (bull/bear)
   - Structure detection (HH/HL, LL/LH)
   
3. **Profile Proxy** (`profile_proxy.py`)
   - VAL/VAH quartile calculation
   - Prior day context alignment
   
4. **Session VWAP** (`vwap.py`)
   - Volume-weighted average price
   - Price vs VWAP alignment
   
5. **ADX** (`adx.py`, `adx_optimized.py`)
   - Wilder's smoothing
   - Trend strength detection
   - Numba-optimized version (50x faster)

---

### 5. Strategy Core (`orb_confluence/strategy/`)

**Purpose**: Signal generation and trade management.

**Key Files:**
- `scoring.py` - Confluence scoring engine
- `breakout.py` - Breakout signal detection
- `trade_state.py` - Trade signal and state dataclasses
- `risk.py` - Stop/target calculation
- `trade_manager.py` - Trade lifecycle management
- `governance.py` - Risk governance rules

**Features:**
- Weighted confluence scoring
- Intrabar breakout detection
- 3 stop modes (OR, swing, ATR-capped)
- Partial targets (T1, T2, runner)
- Breakeven adjustment
- Conservative fill modeling

---

### 6. Governance (`orb_confluence/strategy/governance.py`)

**Purpose**: Enforce risk controls and discipline.

**Rules:**
- Daily signal caps
- Consecutive loss lockouts
- Daily R loss cap (NEW!)
- Time cutoffs
- Session end flattening

---

### 7. Backtest Engine (`orb_confluence/backtest/event_loop.py`)

**Purpose**: Event-driven bar-by-bar simulation.

**Features:**
- No lookahead bias
- Complete module orchestration
- Multi-day support
- Factor sampling
- Trade tracking

---

### 8. Analytics (`orb_confluence/analytics/`)

**Purpose**: Performance analysis and optimization.

**Sub-modules:**
- `metrics.py` - 20+ performance metrics
- `attribution.py` - Factor contribution analysis
- `perturbation.py` - Parameter sensitivity
- `walk_forward.py` - Out-of-sample validation
- `optimization.py` - Hyperparameter tuning (Optuna)

---

### 9. Reporting (`orb_confluence/reporting.py`)

**Purpose**: Generate professional HTML reports.

**Features:**
- Jinja2 templates
- Multiple sections
- Plotly chart embedding
- Auto-save to runs directory

---

### 10. Dashboard (`streamlit_app.py`)

**Purpose**: Interactive web visualization.

**Pages:**
- Performance Summary
- Equity Curve & Drawdown
- Trades Table
- Factor Attribution
- OR Distribution

---

### 11. REST API (`api_server.py`)

**Purpose**: Programmatic access to backtest results.

**Endpoints:**
- `/api/runs` - List runs
- `/api/config/hash` - Config hash
- `/api/trades` - Trades with filters
- `/api/equity` - Equity curve
- `/api/factors/sample` - Factor snapshots
- `/api/metrics/core` - Performance metrics
- `/api/attribution` - Factor attribution

---

### 12. Performance (`orb_confluence/features/adx_optimized.py`, `benchmarks/`)

**Purpose**: Performance optimization and profiling.

**Features:**
- Numba `@njit` optimized ADX (50x speedup)
- Profiling tools (cProfile)
- Benchmark suite
- Hotspot identification

---

## Module Dependencies

```
Data Layer → Features → Strategy → Backtest → Analytics → Reporting
                                             ↓
                                        Governance
```

**Clean separation**: No circular dependencies, modular design.
