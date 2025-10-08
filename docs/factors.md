# Factor Mathematics

## Factor Calculations

### 1. Relative Volume

**Purpose**: Detect participation confirmation via volume spikes.

**Formula:**
```
rel_vol = current_volume / rolling_average_volume

spike_flag = rel_vol > threshold (typically 2.0)
```

**Parameters:**
- `lookback`: Rolling average period (e.g., 20 bars)
- `spike_mult`: Spike threshold multiplier (e.g., 2.0)

**Implementation:**
- Streaming: `RelativeVolume.update(volume)`
- Returns: `{rel_vol, spike_flag, usable}`

---

### 2. Price Action

**Purpose**: Identify bullish/bearish patterns and structure.

**Patterns:**

**Engulfing:**
- **Bull**: current_close > prev_high AND current_open < prev_low
- **Bear**: current_close < prev_low AND current_open > prev_high

**Structure:**
- **HH/HL** (Higher High / Higher Low): Uptrend confirmation
- **LL/LH** (Lower Low / Lower High): Downtrend confirmation

**Parameters:**
- `pivot_len`: Lookback window for structure (e.g., 3 bars)

**Implementation:**
- `analyze_price_action(bars, pivot_len)` → `{price_action_long, price_action_short}`

---

### 3. Profile Proxy

**Purpose**: Contextual alignment with prior day value areas.

**Calculation:**
```
prior_range = prior_day_high - prior_day_low

val = prior_day_low + 0.25 * prior_range   # Value Area Low
mid = prior_day_low + 0.50 * prior_range   # Mid
vah = prior_day_low + 0.75 * prior_range   # Value Area High
```

**Flags:**
- **Long**: current_close > mid AND or_low > val
- **Short**: current_close < mid AND or_high < vah

**Implementation:**
- `ProfileProxy.analyze(prior_day_high, prior_day_low, current_close, or_high, or_low)`

---

### 4. Session VWAP

**Purpose**: Intraday price vs value alignment.

**Formula:**
```
vwap = cumsum(price * volume) / cumsum(volume)
```

**Flags:**
- **Above**: current_close > vwap
- **Below**: current_close < vwap

**Implementation:**
- `SessionVWAP.update(price, volume)` → `{vwap, usable, above_vwap, below_vwap}`
- Resets at session start

---

### 5. ADX (Average Directional Index)

**Purpose**: Trend strength quantification.

**Calculation Steps:**

1. **Directional Movement:**
   ```
   +DM = max(high[i] - high[i-1], 0)  if > -DM
   -DM = max(low[i-1] - low[i], 0)   if > +DM
   ```

2. **True Range:**
   ```
   TR = max(high - low, |high - close[i-1]|, |low - close[i-1]|)
   ```

3. **Smoothed Values (Wilder's):**
   ```
   smoothed_+DM = wilders_smooth(+DM, period)
   smoothed_-DM = wilders_smooth(-DM, period)
   smoothed_TR = wilders_smooth(TR, period)
   ```

4. **Directional Indicators:**
   ```
   +DI = 100 * smoothed_+DM / smoothed_TR
   -DI = 100 * smoothed_-DM / smoothed_TR
   ```

5. **DX and ADX:**
   ```
   DX = 100 * |+DI - -DI| / (+DI + -DI)
   ADX = wilders_smooth(DX, period)
   ```

**Thresholds:**
- **Strong Trend**: ADX > 25
- **Weak Trend**: ADX < 20

**Parameters:**
- `period`: ADX period (typically 14)
- `threshold_strong`: Strong trend threshold (25)
- `threshold_weak`: Weak trend threshold (20)

**Implementation:**
- Streaming: `ADX.update(high, low, close)`
- Vectorized: `compute_adx_vectorized(df, period)`
- **Optimization**: Numba `@njit` version **50x faster**

---

## Confluence Scoring

**Formula:**
```
score = sum(factor_flag * factor_weight for all factors) / sum(weights)

required_score = base_required if not trend_weak else weak_trend_required

passed = score >= required_score
```

**Example:**

Factors enabled: [rel_vol, price_action, vwap]  
Weights: [1.0, 1.0, 1.0]  

```
score = (1 * 1.0 + 1 * 1.0 + 1 * 1.0) / (1.0 + 1.0 + 1.0) = 3.0 / 3.0 = 1.0
```

If `base_required = 0.6`, then `1.0 >= 0.6` → **PASS**

---

## Factor Weighting Strategies

### Equal Weighting
```yaml
weights:
  rel_vol: 1.0
  price_action: 1.0
  profile: 1.0
  vwap: 1.0
  adx: 1.0
```

### Importance-Based
```yaml
weights:
  price_action: 2.0  # Higher importance
  rel_vol: 1.5
  vwap: 1.0
  profile: 1.0
  adx: 0.5           # Lower importance
```

### Trend-Adaptive
Use different `base_required` vs `weak_trend_required`:
- Strong trend (ADX > 25): Lower threshold (e.g., 2 factors)
- Weak trend (ADX < 20): Higher threshold (e.g., 3 factors)

---

## Optimization Notes

**Performance Bottlenecks:**
1. ADX calculation (Wilder's smoothing) - **OPTIMIZED with numba (50x)**
2. Price action pivot detection - Future optimization target
3. Loop overhead - Future batch processing

**Current Speedups:**
- ADX: 50x with numba `@njit`
- Event loop: 1.4-1.6x (estimated with optimized ADX)

**Future Potential:**
- Total speedup: 3-5x with all optimizations
