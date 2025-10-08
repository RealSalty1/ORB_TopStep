# Multi-Instrument Features Documentation

## Overview

This document describes the multi-instrument ranking and visualization features added to the ORB Confluence Strategy platform.

---

## Pre-Session Instrument Ranker

### Purpose

The Pre-Session Ranker analyzes multiple instruments before the trading session begins to identify which ones are most likely to produce high-quality trading opportunities. This helps traders focus their attention on the best setups each day.

### Location

`orb_confluence/analytics/pre_session_ranker.py`

---

### Core Components

#### 1. InstrumentScore Dataclass

Stores comprehensive scoring data for each instrument:

```python
@dataclass
class InstrumentScore:
    symbol: str
    total_score: float
    
    # Component scores (0-1 normalized)
    overnight_range_score: float      # Quality of overnight movement
    or_quality_score: float            # Historical OR validity
    news_risk_penalty: float           # News event risk
    vol_regime_score: float            # Volatility consistency
    expectancy_score: float            # Recent performance
    
    # Metadata
    overnight_range_norm: float        # Overnight range / ADR
    expected_or_width_norm: float
    recent_win_rate: float
    recent_expectancy: float
    recent_trade_count: int
    
    # Recommendation
    priority: int                      # 1 = highest
    recommended_watch: bool
    reason: str
```

#### 2. PreSessionRanker Class

Main ranking engine with configurable weights:

**Configuration Parameters:**
- `weight_overnight`: Weight for overnight range component (default: 0.25)
- `weight_or_quality`: Weight for expected OR quality (default: 0.20)
- `weight_news_risk`: Weight for news risk penalty (default: 0.15)
- `weight_vol_regime`: Weight for volatility regime alignment (default: 0.20)
- `weight_expectancy`: Weight for recent expectancy (default: 0.20)
- `lookback_trades`: Number of recent trades for expectancy calc (default: 50)

---

### Scoring Components

#### 1. Overnight Range Score (0-1)

Evaluates the quality of overnight price movement relative to typical ADR:

| Overnight Range / ADR | Score | Interpretation |
|----------------------|-------|----------------|
| < 0.15               | 0.3   | Too quiet - limited opportunity |
| 0.15 - 0.30          | 0.6   | Moderate movement |
| 0.30 - 0.70          | 1.0   | **Optimal range** - ideal setup |
| 0.70 - 1.00          | 0.7   | High but manageable |
| > 1.00               | 0.4   | Possibly exhausted |

**Rationale:** The optimal range indicates sufficient price discovery overnight without exhausting the day's expected range.

#### 2. OR Quality Score (0-1)

Based on historical OR width normalization:

- Calculates average OR width from last 20 sessions
- Checks if typically within instrument's validity bounds
- Perfect score (1.0) if historical OR consistently valid
- Penalizes if ORs are typically too narrow or too wide

**Rationale:** Instruments that consistently produce valid ORs are more reliable.

#### 3. News Risk Penalty (0-1)

External input for scheduled news events:

- 0.0 = No news risk
- 0.5 = Moderate risk (e.g., Fed minutes)
- 0.8+ = High risk (e.g., NFP, CPI, inventory reports)

**Rationale:** High-impact news events can invalidate technical setups.

#### 4. Volatility Regime Score (0-1)

Measures consistency of current volatility vs recent history:

- Calculates Z-score of overnight range vs last 20 sessions
- Higher score for consistent regimes (low Z-score)
- Lower score for unusual volatility spikes

| Z-Score | Score | Interpretation |
|---------|-------|----------------|
| < 0.5   | 1.0   | Very consistent regime |
| 0.5-1.0 | 0.8   | Moderately consistent |
| 1.0-1.5 | 0.6   | Slightly unusual |
| > 1.5   | 0.4   | Unusual volatility |

**Rationale:** Strategy performs best in consistent volatility regimes.

#### 5. Expectancy Score (0-1)

Based on recent trading performance:

- Uses last N trades (configurable, default 50)
- Calculates average R-multiple
- Maps to 0-1 scale: -1R → 0.0, 0R → 0.5, +1R → 1.0

**Rationale:** Recent performance is a strong indicator of current market alignment.

---

### Usage Example

```python
from orb_confluence.analytics.pre_session_ranker import PreSessionRanker
from datetime import date

# Initialize ranker
ranker = PreSessionRanker(
    weight_overnight=0.25,
    weight_or_quality=0.20,
    weight_news_risk=0.15,
    weight_vol_regime=0.20,
    weight_expectancy=0.20
)

# Update historical data (accumulate over time)
ranker.update_history(
    symbol='ES',
    trading_date=date(2025, 10, 1),
    overnight_high=4500.0,
    overnight_low=4480.0,
    or_width_norm=0.25,
    session_adr=45.0
)

ranker.update_trade_history(
    symbol='ES',
    trade_date=date(2025, 10, 1),
    expectancy_r=1.5,
    win=True
)

# Rank instruments for today
overnight_data = {
    'ES': (4500.0, 4480.0),
    'NQ': (15500.0, 15450.0),
    'CL': (70.5, 70.0),
    'GC': (1950.0, 1945.0),
    '6E': (1.0850, 1.0835)
}

news_events = {
    'CL': 0.8  # EIA inventory report today
}

scores = ranker.rank_instruments(
    instruments=instrument_configs,
    overnight_data=overnight_data,
    trading_date=date(2025, 10, 7),
    news_events=news_events
)

# Get watch list
watch_list = ranker.get_watch_list(scores, max_instruments=3)
print(f"Today's watch list: {', '.join(watch_list)}")

# Print detailed rankings
ranker.print_rankings(scores)
```

**Example Output:**
```
====================================================================================================
PRE-SESSION INSTRUMENT RANKINGS
====================================================================================================
Rank   Symbol   Score    Watch    Reason
----------------------------------------------------------------------------------------------------
1      ES       0.782    ✓ YES    optimal overnight range; good historical OR quality; consistent volatility
2      NQ       0.745    ✓ YES    optimal overnight range; strong recent performance
3      GC       0.612    ✓ YES    neutral conditions
4      6E       0.588      No     poor overnight range; weak recent performance
5      CL       0.445      No     high news risk; poor overnight range
====================================================================================================
Recommended Watch List: ES, NQ, GC
====================================================================================================
```

---

## Multi-Instrument Dashboard Pages

### Location

`orb_confluence/viz/multi_instrument_pages.py`

### Available Pages

#### 1. Multi-Instrument Overview

**Purpose:** Comprehensive portfolio-level performance analysis across all instruments.

**Features:**
- **Portfolio Metrics**
  - Total trades across all instruments
  - Combined P&L and return %
  - Overall win rate
  - Average R-multiple
  - Governance lockout days

- **Per-Instrument Comparison**
  - Side-by-side metric cards
  - Trade count, win rate, total R, expectancy per symbol
  - Sortable comparison table

- **Visualizations**
  - Trade distribution pie chart
  - Total R bar chart (color-coded by performance)
  - Win rate vs expectancy scatter plot (bubble size = trade count)

- **Governance Dashboard**
  - Max daily loss tracking
  - Max drawdown
  - Consecutive loss streaks
  - Concurrent trade limits
  - Capital pacing phase distribution

**When to Use:**
- After running multi-instrument backtests
- To identify which instruments contribute most to portfolio performance
- To analyze governance rule effectiveness
- To compare instrument behavior in parallel

**Data Requirements:**
- Backtest run must contain `per_instrument` summary
- Generated by `MultiInstrumentOrchestrator`

---

#### 2. Pre-Session Rankings

**Purpose:** Visualize daily instrument rankings and score components.

**Features:**
- **Daily Rankings Table**
  - Date selector for historical review
  - Complete rankings with all score components
  - Recommended watch list highlighting
  - Human-readable ranking reasons

- **Score Component Radar Chart**
  - Overlay all instruments
  - Compare relative strengths (overnight range, OR quality, vol regime, expectancy)
  - Identify which factors drive each instrument's rank

- **Score Trends Over Time**
  - Select individual instrument
  - Track total score evolution
  - Track priority rank changes
  - Identify consistency vs volatility in rankings

**When to Use:**
- Before trading day to identify focus instruments
- To analyze which factors most influence rankings
- To identify instruments that consistently rank high/low
- To understand ranking volatility and stability

**Data Requirements:**
- Requires `pre_session_rankings.json` in run directory
- Generated by integrating `PreSessionRanker` into backtest workflow

---

### Integration with Streamlit App

The new pages are integrated into the main navigation:

```python
# In streamlit_app.py
page = st.sidebar.radio(
    "📍 Navigation",
    [
        "Overview",
        "Equity Curve",
        "Trades Table",
        "Trade Charts",
        "Factor Attribution",
        "OR Distribution",
        "Charts",
        "Multi-Instrument",      # NEW
        "Pre-Session Rankings"   # NEW
    ]
)
```

**Navigation Logic:**
- "Multi-Instrument" page automatically detects if run is multi-instrument
- Shows helpful message if run is single-instrument
- "Pre-Session Rankings" page checks for rankings data file
- Provides instructions if data not available

---

## Testing

### Test Coverage

**Location:** `orb_confluence/tests/test_pre_session_ranker.py`

**Test Suite:** 15 comprehensive tests with 86% coverage

**Test Categories:**

1. **Initialization Tests**
   - Ranker setup with custom weights
   - Default parameter validation

2. **History Management Tests**
   - Instrument history updates
   - Trade history updates
   - Automatic pruning (100 sessions, 200 trades max)

3. **Component Scoring Tests**
   - Overnight range scoring (optimal, quiet, exhausted)
   - OR quality scoring
   - News risk penalties
   - Volatility regime consistency
   - Expectancy scoring

4. **Ranking Tests**
   - No historical data (neutral scores)
   - With historical data (differentiation)
   - News risk impact
   - Watch list generation

5. **Statistical Tests**
   - Recent stats calculation
   - History pruning behavior
   - Score normalization (all components 0-1)
   - Reason string generation

**Run Tests:**
```bash
python -m pytest orb_confluence/tests/test_pre_session_ranker.py -v
```

---

## Integration Workflow

### Step 1: Collect Historical Data

During each backtest day, capture:

```python
# After session ends
ranker.update_history(
    symbol=instrument,
    trading_date=current_date,
    overnight_high=overnight_high,
    overnight_low=overnight_low,
    or_width_norm=or_state.width / atr_value,
    session_adr=session_high - session_low
)

# After each trade closes
ranker.update_trade_history(
    symbol=instrument,
    trade_date=trade_date,
    expectancy_r=trade.realized_r,
    win=trade.realized_r > 0
)
```

### Step 2: Generate Pre-Session Rankings

Before each trading day:

```python
# Get overnight data (from data feed or cached data)
overnight_data = get_overnight_ranges(instruments)

# Optional: get news events
news_events = get_scheduled_news_events(date)

# Rank instruments
scores = ranker.rank_instruments(
    instruments=instrument_configs,
    overnight_data=overnight_data,
    trading_date=date,
    news_events=news_events
)

# Save rankings for dashboard
save_rankings_to_json(scores, run_path)

# Get watch list for trading
watch_list = ranker.get_watch_list(scores, max_instruments=3)
```

### Step 3: Use Rankings in Trading

```python
# Only process instruments in watch list
for bar in todays_bars:
    if bar['symbol'] not in watch_list:
        continue  # Skip lower-priority instruments
    
    # Process OR, factors, signals as normal
    process_bar(bar)
```

### Step 4: Visualize in Dashboard

- Load Streamlit dashboard
- Select backtest run
- Navigate to "Pre-Session Rankings"
- Review daily rankings and trends

---

## Configuration Example

### Adjust Ranking Weights

If you want to emphasize recent performance over overnight range:

```python
ranker = PreSessionRanker(
    weight_overnight=0.15,       # Decreased
    weight_or_quality=0.15,      # Decreased
    weight_news_risk=0.10,       # Decreased
    weight_vol_regime=0.20,      # Same
    weight_expectancy=0.40,      # Increased
    lookback_trades=30           # Shorter lookback
)
```

### Set News Risk Manually

```python
# High-impact events
news_events = {
    'CL': 0.9,   # EIA inventory report
    'GC': 0.3,   # Minor geopolitical update
}

# Or use a news calendar API
news_events = fetch_scheduled_events(date)
```

---

## Performance Considerations

### Memory Usage

- **Instrument history:** Max 100 sessions per instrument (~8 KB each)
- **Trade history:** Max 200 trades per instrument (~2 KB each)
- **Total for 5 instruments:** ~50 KB

### Computation Time

- Ranking 5 instruments: ~1-2 ms
- With 20+ sessions of history per instrument: ~5 ms
- Negligible compared to backtest execution time

---

## Future Enhancements

### 1. Machine Learning Integration

Replace manual weights with trained model:

```python
# Train on historical rankings vs actual performance
model = train_ranking_model(historical_rankings, actual_trades)

# Use model to predict optimal instrument
scores = model.predict(overnight_data, history)
```

### 2. Real-Time News Integration

Connect to news APIs for automated risk scoring:

```python
from newsapi import NewsAPIClient

news_events = fetch_news_risk_scores(
    symbols=['ES', 'NQ', 'CL', 'GC', '6E'],
    date=date,
    api_key=api_key
)
```

### 3. Correlation-Based Ranking

Penalize instruments with high correlation to avoid redundant exposure:

```python
# Prefer low-correlation instruments
if correlation(ES, NQ) > 0.8:
    penalize_lower_ranked_of(ES, NQ)
```

### 4. Time-of-Day Profiles

Extend ranking to specific intraday periods:

```python
# Different rankings for OR period vs midday
or_rankings = rank_for_period('or_period')
midday_rankings = rank_for_period('midday')
```

---

## Summary

The Pre-Session Ranker and Multi-Instrument Dashboard provide:

✅ **Objective instrument selection** based on 5 quantitative factors  
✅ **Configurable weighting** to match trader preferences  
✅ **Visual analysis** of rankings and trends  
✅ **Portfolio-level performance** tracking  
✅ **Governance monitoring** across all instruments  
✅ **Comprehensive testing** (15 tests, 86% coverage)  

These features enable traders to:
- Focus on highest-probability setups each day
- Understand why instruments are ranked as they are
- Track multi-instrument portfolio performance
- Make data-driven decisions about instrument selection

---

## Next Steps

1. **Integrate into live workflow:**
   - Fetch overnight ranges from data feed
   - Generate rankings before market open
   - Use watch list to filter trading focus

2. **Backtest with rankings:**
   - Run historical backtests using past rankings
   - Measure performance improvement vs trading all instruments
   - Optimize ranking weights

3. **Extend to more instruments:**
   - Add additional futures contracts (RTY, ZN, ZB)
   - Test with stocks (SPY, QQQ, IWM)
   - Analyze cross-asset ranking consistency

4. **Add more factors:**
   - Options implied volatility
   - Futures term structure
   - Market breadth indicators
   - Sector rotation signals
