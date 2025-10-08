# Configuration Parameter Glossary

## Overview

All strategy parameters are defined in YAML configuration files with Pydantic validation.

**Structure:**
```yaml
instrument:
  symbol: ES
  proxy_symbol: SPY
  ...

orb:
  base_minutes: 15
  adaptive: true
  ...

factors:
  rel_vol:
    lookback: 20
    ...

trade:
  stop_mode: or_opposite
  ...

governance:
  max_signals_per_day: 3
  lockout_after_losses: 2
  max_daily_loss_r: 5.0  # NEW!
  ...
```

---

## Configuration Schemas

### ADXConfig

**Description**: ADX trend regime factor configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean |  | Enable ADX factor |
| `period` | integer |  | ADX calculation period |
| `threshold` | number |  | Minimum ADX for trend |

---

### BacktestConfig

**Description**: Backtest execution configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conservative_fills` | boolean |  | If stop & target both hit in bar, assume stop first |
| `contracts_per_trade` | integer |  | Contracts per trade (fixed) |
| `end_date` | string | ✅ | Backtest end date (YYYY-MM-DD) |
| `initial_capital` | number |  | Initial capital |
| `random_seed` | integer |  | Random seed for reproducibility |
| `start_date` | string | ✅ | Backtest start date (YYYY-MM-DD) |

---

### BuffersConfig

**Description**: Breakout buffer configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `atr_mult` | number |  | ATR buffer multiplier |
| `fixed` | number |  | Fixed buffer (instrument-specific units) |
| `use_atr` | boolean |  | Add ATR-based dynamic buffer |

---

### FactorsConfig

**Description**: All factor configurations.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `adx` | unknown |  | No description |
| `price_action` | unknown |  | No description |
| `profile_proxy` | unknown |  | No description |
| `rel_volume` | unknown |  | No description |
| `vwap` | unknown |  | No description |

---

### GovernanceConfig

**Description**: Risk governance and discipline configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `flatten_at_session_end` | boolean |  | Flatten all positions before session close |
| `lockout_after_losses` | integer |  | Consecutive full-stop losses before lockout |
| `max_daily_loss_r` | unknown |  | Maximum daily loss in R (halts new entries if reached) |
| `max_signals_per_day` | integer |  | Maximum signals per instrument per day |
| `second_chance_minutes` | integer |  | Allow re-break within N minutes after OR |
| `time_cutoff` | unknown |  | No new entries after this time (exchange local) |

---

### InstrumentConfig

**Description**: Instrument configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `data_source` | string | ✅ | Data source: yahoo, binance, synthetic |
| `enabled` | boolean |  | Enable trading this instrument |
| `point_value` | number | ✅ | Dollar value per full point |
| `proxy_symbol` | string | ✅ | Proxy symbol for free data (e.g., SPY) |
| `session_end` | string | ✅ | Session end time (exchange local) |
| `session_mode` | unknown |  | Trading session type |
| `session_start` | string | ✅ | Session start time (exchange local) |
| `symbol` | string | ✅ | Target futures symbol (e.g., ES) |
| `tick_size` | number | ✅ | Minimum price increment |
| `timezone` | string |  | Exchange timezone |

---

### ORBConfig

**Description**: Opening Range configuration with adaptive duration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `adaptive` | boolean |  | Use adaptive OR duration based on volatility |
| `atr_period` | integer |  | ATR lookback period |
| `base_minutes` | integer |  | Base OR duration (minutes) |
| `daily_atr_timeframe` | string |  | Daily ATR timeframe |
| `enable_validity_filter` | boolean |  | Require valid OR width |
| `high_norm_vol` | number |  | Normalized vol threshold for long OR |
| `intraday_atr_timeframe` | string |  | Intraday ATR timeframe |
| `long_or_minutes` | integer |  | Long OR duration (minutes) |
| `low_norm_vol` | number |  | Normalized vol threshold for short OR |
| `max_atr_mult` | number |  | Maximum OR width as ATR multiple |
| `min_atr_mult` | number |  | Minimum OR width as ATR multiple |
| `short_or_minutes` | integer |  | Short OR duration (minutes) |

---

### OptimizationConfig

**Description**: Optimization configuration (optional).

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean |  | Enable parameter optimization |
| `method` | string |  | Optimization method: optuna, grid, random |
| `n_trials` | integer |  | Number of optimization trials |
| `objective` | string |  | Optimization objective: expectancy, sharpe, profit_factor |
| `optimize_params` | array |  | List of parameter paths to optimize (e.g., 'orb.base_minutes') |

---

### PriceActionConfig

**Description**: Price action pattern factor configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enable_engulfing` | boolean |  | Check for engulfing patterns |
| `enable_structure` | boolean |  | Check for HH/HL or LL/LH structure |
| `enabled` | boolean |  | Enable price action factor |
| `pivot_len` | integer |  | Pivot lookback length |

---

### ProfileProxyConfig

**Description**: Profile proxy factor configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean |  | Enable profile proxy factor |
| `vah_pct` | number |  | Value Area High percentile |
| `val_pct` | number |  | Value Area Low percentile |

---

### RelativeVolumeConfig

**Description**: Relative volume factor configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean |  | Enable relative volume factor |
| `lookback` | integer |  | Volume SMA lookback periods |
| `spike_mult` | number |  | Spike threshold multiplier |

---

### ScoringConfig

**Description**: Confluence scoring configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_required` | integer |  | Base score required for entry |
| `enabled` | boolean |  | Enable confluence scoring gate |
| `weak_trend_required` | integer |  | Score required in weak trend (ADX < threshold) |
| `weights` | object |  | Factor weights for scoring |

---

### StrategyConfig

**Description**: Root strategy configuration with full validation.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `backtest` | unknown | ✅ | Backtest parameters |
| `buffers` | unknown |  | No description |
| `factors` | unknown |  | No description |
| `governance` | unknown |  | No description |
| `instruments` | object | ✅ | Instrument configurations |
| `log_level` | string |  | Logging level |
| `log_to_file` | boolean |  | Write logs to file |
| `name` | string |  | Strategy name |
| `optimization` | unknown |  | No description |
| `orb` | unknown |  | No description |
| `scoring` | unknown |  | No description |
| `trade` | unknown |  | No description |
| `version` | string |  | Configuration version |

---

### TradeConfig

**Description**: Trade execution and management configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `atr_stop_cap_mult` | number |  | ATR cap multiplier for stop distance |
| `be_buffer` | number |  | Buffer when moving to breakeven (ticks) |
| `extra_stop_buffer` | number |  | Extra buffer beyond structural stop |
| `move_be_at_r` | number |  | Move stop to breakeven after this R achieved |
| `partials` | boolean |  | Use partial profit targets |
| `primary_r` | number |  | Primary target R when no partials |
| `runner_r` | number |  | Runner target R multiple |
| `stop_mode` | unknown |  | Stop placement mode |
| `t1_pct` | number |  | First target position % |
| `t1_r` | number |  | First target R multiple |
| `t2_pct` | number |  | Second target position % |
| `t2_r` | number |  | Second target R multiple |

---

### VWAPConfig

**Description**: VWAP factor configuration.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `enabled` | boolean |  | Enable VWAP factor |
| `reset_mode` | string |  | VWAP reset point: session or or_end |

---

## Validation Rules

The configuration system enforces these validation rules:

### ORB Configuration
- `min_atr_mult < max_atr_mult` - Minimum must be less than maximum
- `low_norm_vol < high_norm_vol` - Low threshold must be less than high (for adaptive OR)
- `short_or_minutes < long_or_minutes` - Short OR must be shorter than long OR

### Trade Configuration
- `runner_r > 1.5` when `partials = True` - Runner target must be worthwhile
- `t1_r < t2_r < runner_r` - Target progression must increase
- At least one buffer type enabled

### Factors Configuration
- All lookback periods >= 1
- All weights non-negative
- At least one factor enabled

### Governance Configuration
- `max_signals_per_day >= 1`
- `lockout_after_losses >= 1`
- `max_daily_loss_r >= 0` (if set)

### Scoring Configuration
- `base_required <= weak_trend_required` - Base threshold should not exceed weak trend
- All factor weights non-negative

---

## Configuration Loading

### Default Configuration

```python
from orb_confluence.config import load_config

# Load defaults
config = load_config()
```

### User Overrides

```python
# Load with user overrides
config = load_config("my_config.yaml")
```

The loader performs deep merge:
1. Load `defaults.yaml`
2. Load user config
3. Merge (user overrides defaults)
4. Validate with Pydantic
5. Compute config hash (SHA256)

### Configuration Hash

Every configuration gets a unique hash for reproducibility:

```python
config_hash = resolved_config_hash(config)
print(f"Config hash: {config_hash}")
```

Used to track which configuration produced which results.

---

## Example Configurations

### Conservative Strategy

```yaml
orb:
  base_minutes: 30
  min_atr_mult: 0.5
  max_atr_mult: 1.5

trade:
  stop_mode: or_opposite
  t1_r: 1.0
  runner_r: 2.0
  partials: false

governance:
  max_signals_per_day: 2
  lockout_after_losses: 1
  max_daily_loss_r: 3.0

scoring:
  base_required: 3
  weak_trend_required: 4
```

### Aggressive Strategy

```yaml
orb:
  base_minutes: 10
  adaptive: true
  min_atr_mult: 0.2
  max_atr_mult: 2.0

trade:
  stop_mode: atr_capped
  t1_r: 0.8
  t2_r: 1.5
  runner_r: 3.0
  partials: true

governance:
  max_signals_per_day: 5
  lockout_after_losses: 3
  max_daily_loss_r: 8.0

scoring:
  base_required: 2
  weak_trend_required: 3
```

---

**Version**: 1.0  
**Last Updated**: 2024
